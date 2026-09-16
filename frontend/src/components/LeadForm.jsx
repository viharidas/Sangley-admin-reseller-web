import React,{useState} from 'react';
import {Check} from 'lucide-react';
import {useStore,api,errorText,attribution,track} from '../lib/store';
import {Action} from './Elements';

export const LeadForm=({type='reseller',starter='',onStarterChange})=>{
  const {content}=useStore();
  const [busy,setBusy]=useState(false),[success,setSuccess]=useState(null),[error,setError]=useState('');
  const submit=async e=>{
    e.preventDefault();setBusy(true);setError('');
    const data=Object.fromEntries(new FormData(e.currentTarget));
    data.consent=data.consent==='on';data.type=type;data.attribution=attribution();
    if(!data.email)delete data.email;
    if(!data.whatsapp)data.whatsapp=data.mobile;
    try{const r=await api.post('/leads',data);setSuccess(r.data);track(type==='reseller'?'reseller_lead':'consumer_lead',{starter_option:data.starter_option,lead_id:r.data.id});}
    catch(e){setError(errorText(e));}finally{setBusy(false);}
  };
  if(success)return <div className="form-success" data-testid="lead-success"><div><Check size={35}/></div><span className="eyebrow">A NEW CHAPTER STARTS HERE</span><h2>YOU’RE IN<br/><span className="serif-accent">good company.</span></h2><p>{success.message}</p><Action to="/shop" testId="lead-success-shop">MEET THE FLAVOURS</Action></div>;
  return <form onSubmit={submit} className="lead-form" data-testid="lead-form">
    <div className="form-grid">
      <label>YOUR NAME<input name="name" data-testid="lead-name" autoComplete="name" required minLength={2} maxLength={120} placeholder="What should we call you?"/></label>
      <label>MOBILE NUMBER<input name="mobile" data-testid="lead-mobile" autoComplete="tel" inputMode="tel" required pattern="\+?[0-9 ]{10,15}" placeholder="Your 10-digit mobile number"/></label>
      <label>CITY<input name="city" data-testid="lead-city" autoComplete="address-level2" required minLength={2} placeholder="Where’s your community?"/></label>
      {type==='reseller'?<label>COMMUNITY TYPE<select name="community_type" data-testid="lead-community" required defaultValue=""><option value="" disabled>Choose your community</option>{['Housing society','Friends & family','Office','College','WhatsApp groups','Neighbourhood','Other'].map(x=><option key={x}>{x}</option>)}</select></label>:<label>EMAIL (OPTIONAL)<input name="email" type="email" data-testid="lead-email" placeholder="you@example.com"/></label>}
      {type==='reseller'&&<>
        <label>APPROXIMATE NETWORK SIZE<select name="network_size" data-testid="lead-network" defaultValue=""><option value="">Choose a range (optional)</option>{['Under 25 people','25–50 people','51–100 people','100+ people'].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>STARTING OPTION<select name="starter_option" data-testid="lead-starter" value={starter} onChange={e=>{onStarterChange?.(e.target.value);track('starter_kit_selection',{kit:e.target.value});}}><option value="">Help me decide</option>{content.reseller.kits.filter(k=>k.enabled).map(k=><option key={k.id} value={k.id}>{k.name}</option>)}</select></label>
        <label className="full-span">WHATSAPP NUMBER (IF DIFFERENT)<input name="whatsapp" data-testid="lead-whatsapp" inputMode="tel" pattern="\+?[0-9 ]{10,15}" placeholder="Leave empty to use your mobile number"/></label>
      </>}
      {type!=='reseller'&&<label className="full-span">WHAT’S ON YOUR MIND?<textarea name="message" data-testid="lead-message" required rows={4} maxLength={2000} placeholder="An order question, a collaboration, or just a hello…"/></label>}
    </div>
    <label className="consent"><input name="consent" type="checkbox" required data-testid="lead-consent"/><span>I agree to be contacted by SANGLEY about my enquiry. <a href="/policies/privacy" target="_blank" rel="noreferrer" data-testid="lead-privacy">Privacy information</a></span></label>
    {error&&<p role="alert" className="error-text" data-testid="lead-error">{error}</p>}
    <Action type="submit" className="full-width" disabled={busy} testId="lead-submit">{busy?'SENDING…':type==='reseller'?'START MY SANGLEY JOURNEY':'SEND MY MESSAGE'}</Action>
    <p className="small-note">A real conversation. No pressure. No payment at this step.</p>
  </form>;
};