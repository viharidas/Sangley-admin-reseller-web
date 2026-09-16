import React,{useEffect,lazy,Suspense} from 'react';
import {BrowserRouter,Routes,Route,useLocation} from 'react-router-dom';
import Lenis from 'lenis';
import {useReducedMotion} from 'framer-motion';
import {Toaster} from './components/ui/sonner';
import {StoreProvider,useStore,track} from './lib/store';
import {Header,Footer,CartDrawer,FloatingContact} from './components/Layout';
import Home from './pages/Home';
import Shop,{Combos} from './pages/Shop';
import Product from './pages/Product';
import Resell from './pages/Resell';
import Checkout from './pages/Checkout';
import {Story,FAQ,Contact,Policy,Offers,Account,NotFound} from './pages/Information';
import './App.css';
const Admin=lazy(()=>import('./pages/Admin'));

const ScrollManager=()=>{const {pathname,hash}=useLocation();const reduced=useReducedMotion();useEffect(()=>{if(reduced)return;const lenis=new Lenis({duration:1.05,smoothWheel:true,anchors:true,autoRaf:true,prevent:node=>node.hasAttribute('data-lenis-prevent')});window.sangleyLenis=lenis;return()=>{lenis.destroy();delete window.sangleyLenis;};},[reduced]);useEffect(()=>{if(!hash){window.sangleyLenis?.scrollTo(0,{immediate:true});window.scrollTo(0,0);}else{const timer=setTimeout(()=>{try{document.querySelector(hash)?.scrollIntoView({behavior:reduced?'instant':'smooth'});}catch{}},120);return()=>clearTimeout(timer);}track('page_view');},[pathname,hash,reduced]);return null;};
const Site=()=>{const {loading,error,reload}=useStore();const {pathname}=useLocation();const admin=pathname.startsWith('/admin');if(loading)return <div className="loading-screen" data-testid="site-loading"><span>SANGLEY</span><p>A LITTLE CRUNCH IS ON ITS WAY.</p><div/></div>;if(error)return <div className="loading-screen" data-testid="site-error"><span>SANGLEY</span><p>{error}</p><button className="s-button" data-testid="site-retry" onClick={reload}>TRY AGAIN</button></div>;return <><ScrollManager/>{!admin&&<Header/>}<main id="main-content"><Suspense fallback={<div className="loading-screen">LOADING YOUR SANGLEY SPACE…</div>}><Routes><Route path="/" element={<Home/>}/><Route path="/shop" element={<Shop/>}/><Route path="/collections/combos" element={<Combos/>}/><Route path="/products/:handle" element={<Product/>}/><Route path="/resell-with-sangley" element={<Resell/>}/><Route path="/our-story" element={<Story/>}/><Route path="/faq" element={<FAQ/>}/><Route path="/contact" element={<Contact/>}/><Route path="/policies/:type" element={<Policy/>}/><Route path="/offers" element={<Offers/>}/><Route path="/account" element={<Account/>}/><Route path="/checkout" element={<Checkout/>}/><Route path="/admin/*" element={<Admin/>}/><Route path="*" element={<NotFound/>}/></Routes></Suspense></main>{!admin&&<><Footer/><CartDrawer/><FloatingContact/></>}<Toaster position="bottom-center" theme="light"/></>};
export default function App(){return <BrowserRouter><StoreProvider><a className="skip-link" href="#main-content" data-testid="skip-to-content">Skip to content</a><Site/></StoreProvider></BrowserRouter>};