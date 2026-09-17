import axios from 'axios';
import {useEffect,useState,useCallback,useRef} from 'react';
export {errorText,money} from '../lib/store';
export const root=process.env.REACT_APP_BACKEND_URL;
export const rApi=axios.create({baseURL:`${root}/api/reseller`,withCredentials:true});
export const bApi=axios.create({baseURL:`${root}/api/admin/business`,withCredentials:true});
export const fileApi=axios.create({baseURL:`${root}/api`,withCredentials:true});
rApi.interceptors.response.use(r=>r,async error=>{
 const c=error.config;
 if(error.response?.status===401&&c&&!c._retry&&(!c.url.startsWith('/auth/')||c.url==='/auth/me')){c._retry=true;try{await rApi.post('/auth/refresh');return rApi(c);}catch{}}
 return Promise.reject(error);
});
bApi.interceptors.response.use(r=>r,async error=>{
 const c=error.config;if(error.response?.status===401&&c&&!c._retry){c._retry=true;try{await fileApi.post('/auth/refresh');return bApi(c);}catch{}}return Promise.reject(error);
});
fileApi.interceptors.response.use(r=>r,async error=>{
 const c=error.config;if(error.response?.status===401&&c&&!c._retry&&!c.url.startsWith('/auth/')){c._retry=true;try{await fileApi.post('/auth/refresh');return fileApi(c);}catch{try{await rApi.post('/auth/refresh');return fileApi(c);}catch{}}}return Promise.reject(error);
});
export const cash=n=>n==null?'—':new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',minimumFractionDigits:0,maximumFractionDigits:2}).format(n/100);
export const dateLabel=value=>value?new Date(value).toLocaleDateString('en-IN',{day:'numeric',month:'short',year:'numeric'}):'—';
export const useResource=(url,client=rApi)=>{
 const clientRef=useRef(client);clientRef.current=client;const baseURL=client.defaults?.baseURL;
 const [data,setData]=useState(null),[loading,setLoading]=useState(true),[error,setError]=useState(null);
 const load=useCallback(async()=>{if(!url){setLoading(false);return;}setLoading(true);setError(null);try{const r=await clientRef.current.get(url);setData(r.data);return r.data;}catch(e){setError(e);}finally{setLoading(false);}},[url,baseURL]);
 useEffect(()=>{load();},[load]);return {data,loading,error,reload:load,setData};
};
export const saveBlob=(blob,name)=>{const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1500);};
export const downloadAsset=async asset=>{if(asset.file_id){const result=await fileApi.get(`/portal-files/${asset.file_id}?download=true`,{responseType:'blob'});saveBlob(result.data,asset.title||'SANGLEY-resource');}else window.open(asset.url,'_blank','noopener,noreferrer');};