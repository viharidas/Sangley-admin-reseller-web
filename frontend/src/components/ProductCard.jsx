import React from 'react';
import { Link } from 'react-router-dom';
import { Plus, Heart, ArrowUpRight } from 'lucide-react';
import { useStore, money } from '../lib/store';
import { Reveal } from './Elements';

export const ProductCard=({product:p,index=0,prefix='product'})=>{
  const {addItem,wishlist,toggleWish}=useStore();
  return <Reveal className="product-card" delay={index*.07} data-testid={`${prefix}-${p.id}`}>
    <div className="product-art" style={{background:p.background}}>
      <span className="product-index" data-testid={`${prefix}-${p.id}-index`}>0{index+1} / THE {p.flavour.toUpperCase()}</span>
      {p.badge&&<span className="product-badge" data-testid={`${prefix}-${p.id}-badge`}>{p.badge}</span>}
      <button className={`wish ${wishlist.includes(p.id)?'saved':''}`} data-testid={`${prefix}-${p.id}-wishlist`} aria-label={`${wishlist.includes(p.id)?'Remove':'Save'} ${p.title} ${wishlist.includes(p.id)?'from':'to'} wishlist`} onClick={()=>toggleWish(p.id)}><Heart size={18} fill={wishlist.includes(p.id)?'currentColor':'none'}/></button>
      <Link to={`/products/${p.handle}`} data-testid={`${prefix}-${p.id}-image-link`} className="pack-link"><img src={p.images[0]} alt={`${p.title}, ${p.weight}g${p.concept_images?' — concept packaging':''}`} loading="lazy" data-testid={`${prefix}-${p.id}-image`}/></Link>
      {p.concept_images&&<span className="concept-label" data-testid={`${prefix}-${p.id}-concept`}>CONCEPT PACKAGING</span>}
    </div>
    <div className="product-details"><div><Link data-testid={`${prefix}-${p.id}-title`} to={`/products/${p.handle}`}><h3>{p.flavour.toUpperCase()} <ArrowUpRight size={18}/></h3></Link><p data-testid={`${prefix}-${p.id}-personality`}>{p.personality}</p><div className="product-price" data-testid={`${prefix}-${p.id}-price`}>{money(p.price)}<span> / {p.weight}g</span></div></div><button className="quick-add" disabled={!p.available} data-testid={`${prefix}-${p.id}-add`} aria-label={`Add ${p.title} to cart`} onClick={()=>addItem({product_id:p.id,quantity:1})}><Plus size={22}/></button></div>
    {!p.available&&<p className="muted" data-testid={`${prefix}-${p.id}-unavailable`}>Currently unavailable</p>}
  </Reveal>;
};