import React,{useState} from 'react';
import {Link,useSearchParams} from 'react-router-dom';
import {SlidersHorizontal,ArrowUpRight} from 'lucide-react';
import {useStore,money} from '../lib/store';
import {ProductCard} from '../components/ProductCard';
import {SEO,Chapter,Star,Empty,Reveal} from '../components/Elements';
import {BundleBuilder} from '../components/BundleBuilder';

export default function Shop(){
  const {products}=useStore();
  const [flavour,setFlavour]=useState('all'),[sort,setSort]=useState('featured'),[availability,setAvailability]=useState('all'),[maxPrice,setMaxPrice]=useState(''),[size,setSize]=useState('all');
  let filtered=products.filter(p=>(flavour==='all'||p.flavour===flavour)&&(availability==='all'||p.available===(availability==='available'))&&(!maxPrice||p.price<=Number(maxPrice))&&(size==='all'||p.weight===Number(size)));
  filtered=[...filtered].sort((a,b)=>sort==='price-low'?a.price-b.price:sort==='price-high'?b.price-a.price:sort==='newest'?b.created_at.localeCompare(a.created_at):sort==='best-selling'?b.sales_count-a.sales_count:a.featured_order-b.featured_order);
  return <>
    <SEO title="Shop Bhadang"/>
    <div className="page-intro container"><Chapter number="01">THE SANGLEY COLLECTION</Chapter><div className="page-intro-row"><h1>FIND YOUR<br/><span className="serif-accent">kind of crunch.</span></h1><div><p>Four flavours. Plenty of personality.<br/>Start with one. Come back for the others.</p><Link to="/collections/combos" className="inline-action" data-testid="shop-combos">FEELING SOCIAL? BUILD A BOX <ArrowUpRight size={18}/></Link></div></div></div>
    <section className="container shop-main">
      <div className="shop-filters">
        <div className="filter-chips" aria-label="Flavour filters">{['all',...new Set(products.map(p=>p.flavour))].map(f=><button key={f} data-testid={`filter-${f.toLowerCase().replaceAll(' ','-')}`} className={flavour===f?'active':''} onClick={()=>setFlavour(f)}>{f==='all'?'ALL BHADANG':f.toUpperCase()}</button>)}</div>
        <label className="sort-label"><span>Sort by</span><select data-testid="shop-sort" value={sort} onChange={e=>setSort(e.target.value)}><option value="featured">Featured</option><option value="best-selling">Best selling</option><option value="price-low">Price: low to high</option><option value="price-high">Price: high to low</option><option value="newest">Newest</option></select></label>
      </div>
      <div className="shop-secondary-filters">
        <span><SlidersHorizontal size={15}/> FILTERS</span>
        <select aria-label="Availability" data-testid="shop-availability" value={availability} onChange={e=>setAvailability(e.target.value)}><option value="all">Any availability</option><option value="available">Available</option><option value="unavailable">Unavailable</option></select>
        <select aria-label="Pack size" data-testid="shop-pack-size" value={size} onChange={e=>setSize(e.target.value)}><option value="all">All pack sizes</option>{[...new Set(products.map(p=>p.weight))].map(w=><option key={w} value={w} label={`${w}g`}/>)}</select>
        <input type="number" min="0" aria-label="Maximum price" data-testid="shop-max-price" placeholder="Max price ₹" value={maxPrice} onChange={e=>setMaxPrice(e.target.value)}/>
        <span className="product-count" data-testid="shop-product-count">{filtered.length} {filtered.length===1?'flavour':'flavours'}</span>
      </div>
      {filtered.length?<div className="product-grid shop-grid">{filtered.map((p,i)=><ProductCard key={p.id} product={p} index={i} prefix="shop-product"/>)}</div>:<Empty title="NOT A CRUNCH IN SIGHT." description="Try a different filter to find your flavour."/>}
      <div className="shop-combo-banner"><Star/><div><h2>WHY PICK ONE?</h2><p>Same flavour or mix & match. Your 4, 6 or 8-pack box awaits.</p></div><Link data-testid="shop-build-box" className="inline-action" to="/collections/combos">BUILD MY BOX <ArrowUpRight/></Link></div>
    </section>
  </>;
}

export function Combos(){
  const {content,products}=useStore();const [params]=useSearchParams();
  const [size,setSize]=useState(Number(params.get('size'))||4),[version,setVersion]=useState(0);
  const min=Math.min(...products.filter(p=>p.available).map(p=>p.price));
  return <>
    <SEO title="Your crunch. Your combo."/>
    <div className="page-intro container"><Chapter number="02">THE SANGLEY BOX CLUB</Chapter><div className="page-intro-row"><h1>YOUR CRUNCH.<br/><span className="serif-accent">Your combo.</span></h1><p>For the family. For the office. For yourself.<br/>There’s no wrong way to fill a SANGLEY box.</p></div></div>
    <section className="container combo-destination">
      <div className="combo-recommendations">{content.bundles.filter(b=>b.enabled).map((b,i)=><Reveal key={b.size} delay={i*.1}><button className={size===b.size?'combo-option active':'combo-option'} data-testid={`combo-recommendation-${b.size}`} onClick={()=>{setSize(b.size);setVersion(v=>v+1);document.getElementById('build-your-box')?.scrollIntoView({behavior:'smooth'});}}><span className="eyebrow">{b.recommendation}</span><div><strong>{b.size}</strong><span>PACK<br/>BOX</span><ArrowUpRight/></div><h3>{b.title}</h3><p>{b.use_case}</p><span className="combo-option-price">{b.price!=null?money(b.price):`From ${Number.isFinite(min)?money(min*b.size):'—'}`}</span>{b.offer&&<small>{b.offer}</small>}</button></Reveal>)}</div>
      <div id="build-your-box"><BundleBuilder key={version} initialSize={size}/></div>
      <div className="use-cases" data-testid="combo-use-cases">MADE FOR YOUR EVERYDAY <span>OFFICE BREAKS</span><span>FAMILY TIME</span><span>PARTIES</span><span>GIFTING</span><span>STOCKING UP</span></div>
    </section>
  </>;
}