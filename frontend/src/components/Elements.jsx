import React, { useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { motion, useReducedMotion } from 'framer-motion';
import { ArrowUpRight, ArrowRight, Plus, Minus } from 'lucide-react';
import { Button } from './ui/button';
import { useStore, track } from '../lib/store';

export const Action=({children,to,onClick,light=false,outline=false,testId,className='',...props})=>{
  const cls=`s-button ${light?'light':''} ${outline?'outline':''} ${className}`;
  return to?<Button asChild className={cls}><Link to={to} data-testid={testId} onClick={onClick} {...props}>{children}<ArrowUpRight size={18}/></Link></Button>:<Button className={cls} data-testid={testId} onClick={onClick} {...props}>{children}<ArrowUpRight size={18}/></Button>;
};
export const Reveal=({children,className='',delay=0,...props})=>{
  const reduced=useReducedMotion();
  return <motion.div className={className} initial={reduced?false:{opacity:0,y:28}} whileInView={{opacity:1,y:0}} viewport={{once:true,amount:.12}} transition={{duration:.7,delay,ease:[.22,1,.36,1]}} {...props}>{children}</motion.div>;
};
export const Chapter=({number,children,light=false})=><div className={`chapter ${light?'on-dark':''}`} data-testid={`chapter-${number}`}><span>({number})</span><span>{children}</span><span className="chapter-line"/><span className="chapter-star" aria-hidden="true">✳</span></div>;
export const Counter=({value,onChange,max=100,testId})=><div className="counter" data-testid={`${testId}-control`}><button type="button" aria-label="Decrease quantity" data-testid={`${testId}-minus`} disabled={value<=0} onClick={()=>onChange(value-1)}><Minus size={14}/></button><output data-testid={`${testId}-value`}>{value}</output><button type="button" aria-label="Increase quantity" data-testid={`${testId}-plus`} disabled={value>=max} onClick={()=>onChange(value+1)}><Plus size={14}/></button></div>;
export const Star=({className=''})=><svg className={className} viewBox="0 0 100 100" fill="currentColor" aria-hidden="true"><path d="M50 0 59 32 85 15 68 41 100 50 68 59 85 85 59 68 50 100 41 68 15 85 32 59 0 50 32 41 15 15 41 32Z"/></svg>;
export const WhatsAppCTA=({testId='whatsapp-cta',className='',children='START ON WHATSAPP'})=>{
  const {content}=useStore();
  const click=()=>track(content?.whatsapp_number?'whatsapp_click':'reseller_cta_click');
  return content?.whatsapp_number?<a className={`s-button ${className}`} data-testid={testId} href={`https://wa.me/${content.whatsapp_number}?text=${encodeURIComponent('Hi SANGLEY, I want to know about becoming a reseller.')}`} target="_blank" rel="noopener noreferrer" onClick={click}>{children}<ArrowUpRight size={18}/></a>:<Action to="/resell-with-sangley#join" testId={testId} className={className} onClick={click}>LET’S TALK SANGLEY</Action>;
};
export const FAQList=({limit,prefix='faq'})=>{const {content}=useStore();return <div className="faq-list">{content?.faqs.slice(0,limit).map((f,i)=><details key={i} data-testid={`${prefix}-item-${i}`}><summary data-testid={`${prefix}-question-${i}`}><span>{f.question}</span><Plus size={19}/></summary><p data-testid={`${prefix}-answer-${i}`}>{f.answer}</p></details>)}</div>;};
export const SEO=({title='Small town. Big crunch.',description='SANGLEY: Maharashtra-born Bhadang in four flavours. Discover your crunch, build a box, or start community reselling.',product})=>{
  const {pathname}=useLocation();
  useEffect(()=>{document.title=`${title} | SANGLEY`; const set=(name,content,property=false)=>{const attr=property?'property':'name';let tag=document.querySelector(`meta[${attr}="${name}"]`);if(!tag){tag=document.createElement('meta');tag.setAttribute(attr,name);document.head.appendChild(tag);}tag.content=content;};set('description',description);set('og:title',`${title} | SANGLEY`,true);set('og:description',description,true);set('og:url',`${process.env.REACT_APP_BACKEND_URL}${pathname}`,true);set('og:type',product?'product':'website',true);set('og:image',`${process.env.REACT_APP_BACKEND_URL}/assets/classic.webp`,true);let canonical=document.querySelector('link[rel="canonical"]');if(!canonical){canonical=document.createElement('link');canonical.rel='canonical';document.head.appendChild(canonical);}canonical.href=`${process.env.REACT_APP_BACKEND_URL}${pathname}`;const tag=document.createElement('script');tag.type='application/ld+json';tag.id='sangley-schema';tag.textContent=JSON.stringify(product?{'@context':'https://schema.org','@type':'Product',name:product.title,sku:product.sku,brand:{'@type':'Brand',name:'SANGLEY'},description:product.description,image:product.images.map(x=>x.startsWith('/')?`${process.env.REACT_APP_BACKEND_URL}${x}`:x)}:{'@context':'https://schema.org','@type':'Organization',name:'SANGLEY',url:process.env.REACT_APP_BACKEND_URL});document.getElementById('sangley-schema')?.remove();document.head.appendChild(tag);return()=>tag.remove();},[title,description,pathname,product]);return null;
};
export const Empty=({title,description,to,cta})=>{const {setCartOpen}=useStore();return <div className="empty-state" data-testid="empty-state"><Star/><h2>{title}</h2><p>{description}</p>{to&&<Action to={to} testId="empty-state-action" onClick={()=>setCartOpen(false)}>{cta}</Action>}</div>;};