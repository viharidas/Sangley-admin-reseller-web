import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { toast } from 'sonner';

export const api = axios.create({ baseURL: `${process.env.REACT_APP_BACKEND_URL}/api`, withCredentials: true });
api.interceptors.response.use(r=>r,async error=>{
  const config=error.config;
  if(error.response?.status===401 && config && !config._retry && (!config.url.startsWith('/auth/') || config.url==='/auth/me')) {
    config._retry=true;
    try { await api.post('/auth/refresh'); return api(config); } catch (_) { /* Login is required. */ }
  }
  return Promise.reject(error);
});
export const money = value => new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',minimumFractionDigits:0,maximumFractionDigits:2}).format(value ?? 0);
export const errorText = e => {const d=e.response?.data?.detail;return typeof d==='string'?d:Array.isArray(d)?d.map(x=>x.msg).join('. '):'Something went wrong. Please try again.';};
const stored=(key,fallback)=>{try{return JSON.parse(localStorage.getItem(key))??fallback;}catch{return fallback;}};
export const attribution=()=>{let saved={};try{saved=JSON.parse(sessionStorage.getItem('sangley-source')||'{}');}catch{} const params=new URLSearchParams(window.location.search); ['utm_source','utm_medium','utm_campaign','utm_content','utm_term','fbclid'].forEach(k=>{if(params.has(k))saved[k]=params.get(k);});sessionStorage.setItem('sangley-source',JSON.stringify(saved));return saved;};
export const track=(name,properties={})=>{
  let sid=sessionStorage.getItem('sangley-session');if(!sid){sid=crypto.randomUUID();sessionStorage.setItem('sangley-session',sid);}
  const event={name,properties,session_id:sid,path:window.location.pathname,audience:window.location.pathname.includes('resell')?'reseller':'consumer',attribution:attribution()};
  window.dataLayer=window.dataLayer||[];window.dataLayer.push({event:name,...event});
  api.post('/events',event).catch(()=>{});
};
const Store=createContext(null);
export const StoreProvider=({children})=>{
  const [products,setProducts]=useState([]),[content,setContent]=useState(null),[loading,setLoading]=useState(true),[error,setError]=useState('');
  const [cart,setCart]=useState(()=>stored('sangley-cart-v1',[])),[cartOpen,setCartOpen]=useState(false),[wishlist,setWishlist]=useState(()=>stored('sangley-wishlist',[]));
  const [quote,setQuote]=useState(null),[quoteError,setQuoteError]=useState(''),[quoting,setQuoting]=useState(false);
  const reload=useCallback(async()=>{try{const [p,c]=await Promise.all([api.get('/products'),api.get('/content')]);setProducts(p.data);setContent(c.data);setError('');}catch(e){setError('We couldn’t load the crunch. Please try again.');}finally{setLoading(false);}},[]);
  useEffect(()=>{reload();},[reload]);
  useEffect(()=>{if(content?.theme)Object.entries(content.theme).forEach(([k,v])=>document.documentElement.style.setProperty(`--${k}`,v));},[content]);
  useEffect(()=>{localStorage.setItem('sangley-cart-v1',JSON.stringify(cart));setQuoteError('');if(!cart.length){setQuote(null);setQuoting(false);return;}let active=true;setQuoting(true);api.post('/cart/quote',{items:cart}).then(r=>{if(active)setQuote(r.data);}).catch(e=>{if(active){setQuote(null);setQuoteError(errorText(e));}}).finally(()=>{if(active)setQuoting(false);});return()=>{active=false;};},[cart,products,content]);
  useEffect(()=>{localStorage.setItem('sangley-wishlist',JSON.stringify(wishlist));},[wishlist]);
  const addItem=(item,open=true)=>{
    const key=item.bundle_size?`box-${item.bundle_size}-${JSON.stringify(Object.entries(item.selections).sort())}`:item.product_id;
    setCart(old=>{const found=old.find(x=>x.key===key);return found?old.map(x=>x.key===key?{...x,quantity:Math.min(100,x.quantity+item.quantity)}:x):[...old,{...item,key}];});
    track('add_to_cart',{product_id:item.product_id,bundle_size:item.bundle_size,quantity:item.quantity});if(open)setCartOpen(true);else toast.success('Added to your crunch collection');
  };
  const updateQuantity=(key,quantity)=>setCart(old=>quantity<=0?old.filter(x=>x.key!==key):old.map(x=>x.key===key?{...x,quantity:Math.min(quantity,100)}:x));
  const toggleWish=id=>setWishlist(old=>old.includes(id)?old.filter(x=>x!==id):[...old,id]);
  return <Store.Provider value={{products,content,loading,error,reload,cart,setCart,cartOpen,setCartOpen,addItem,updateQuantity,quote,quoteError,quoting,wishlist,toggleWish}}>{children}</Store.Provider>;
};
export const useStore=()=>useContext(Store);