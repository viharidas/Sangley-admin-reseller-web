from pathlib import Path
import requests
import numpy as np
from PIL import Image, ImageFilter
from scipy.ndimage import binary_propagation
from io import BytesIO

ROOT=Path('/app/frontend/public/assets')
ROOT.mkdir(parents=True,exist_ok=True)
images={
'classic':'2b15e7d49f80b040ee4d4d83d45d91c939a2f2465bde1f9da752e718cbbcffe7',
'garlic':'7025a1e45bbe221b056209b75bf6209c1852c0e5241c8606a48fd8a447dd254d',
'peri-peri':'6144aa55edc46791475aaac24451835dd7c402e13d89fbbab6084d3e01c9fe31',
'diet':'32e8d69728bdbf74f25502ddf01550ac6528ee1e4bd1d9895f907fdc53eedf49',
'crunch':'220835aa0383b1585447a18d19d1725c47140ec03e0eef42b9ec1aebc1a9fad6'}
for name,key in images.items():
    url=f'https://static.prod-images.emergentagent.com/jobs/b011b25b-a0ca-40ef-ad75-3a28283c9bad/images/{key}.jpeg'
    response=requests.get(url,timeout=45); response.raise_for_status()
    im=Image.open(BytesIO(response.content)).convert('RGB')
    if name!='crunch':
        a=np.array(im).astype(int)
        neutral=(a.max(axis=2)-a.min(axis=2)<23)&(a.min(axis=2)>90)
        edges=np.zeros(neutral.shape,dtype=bool)
        edges[0,:]=neutral[0,:]; edges[-1,:]=neutral[-1,:]; edges[:,0]=neutral[:,0]; edges[:,-1]=neutral[:,-1]
        outside=binary_propagation(edges,mask=neutral)
        alpha=Image.fromarray(np.where(outside,0,255).astype('uint8')).filter(ImageFilter.GaussianBlur(.45))
        im=im.convert('RGBA'); im.putalpha(alpha)
        bbox=alpha.getbbox()
        if bbox: im=im.crop(bbox)
        im.thumbnail((650,950))
    else: im.thumbnail((900,900))
    im.save(ROOT/f'{name}.webp','WEBP',quality=88)
    print(name,im.size,(ROOT/f'{name}.webp').stat().st_size)