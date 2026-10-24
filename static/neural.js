'use strict';
// Decorative neural sphere. Animation represents UI activity, not model internals.
(() => {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const points = Array.from({length: 90}, (_, i) => {
    const y = 1 - 2 * (i + .5) / 90, r = Math.sqrt(1-y*y), a = i * 2.399963;
    return [Math.cos(a)*r, y, Math.sin(a)*r];
  });
  const edges = [];
  points.forEach((a,i) => points.forEach((b,j) => {
    if(j > i && Math.hypot(...a.map((v,k)=>v-b[k])) < .55) edges.push([i,j]);
  }));
  const surfaces = [...document.querySelectorAll('.neural-canvas')].map(canvas=>({canvas,ctx:canvas.getContext('2d')}));
  let frame = 0, last = 0, phase = 0;
  function draw(now) {
    frame = 0;
    if(document.hidden) return;
    const active = document.body.classList.contains('thinking');
    const dt = Math.min((now-last)||0,50); last=now;
    if(!reduce.matches) phase += dt * (active ? .0005 : .00012);
    for(const {canvas,ctx} of surfaces) {
      if(!ctx || !canvas.getClientRects().length) continue;
      const w=canvas.clientWidth,h=canvas.clientHeight,dpr=Math.min(devicePixelRatio||1,2);
      if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);}
      ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);
      const cx=w/2,cy=h/2,r=Math.min(w,h)*.34;
      const glow=ctx.createRadialGradient(cx,cy,0,cx,cy,r*1.6);
      glow.addColorStop(0,active?'#25f5dc40':'#13cbe528');glow.addColorStop(.65,'#096c9a12');glow.addColorStop(1,'#00000000');
      ctx.fillStyle=glow;ctx.fillRect(0,0,w,h);
      ctx.strokeStyle='#46d9ef29';ctx.lineWidth=.7;
      for(let k=0;k<3;k++){ctx.beginPath();ctx.ellipse(cx,cy,r*(1.21+k*.13),r*(.43+k*.16),phase*.2+k*.9,0,Math.PI*2);ctx.stroke();}
      const projected=points.map(([x,y,z])=>{
        const xx=x*Math.cos(phase)+z*Math.sin(phase),zz=z*Math.cos(phase)-x*Math.sin(phase),yy=y*.94-zz*.2;
        return [cx+xx*r,cy+yy*r,zz];
      });
      edges.forEach(([i,j],k)=>{
        const a=projected[i],b=projected[j],alpha=.08+(a[2]+b[2]+2)*.075;
        ctx.strokeStyle=`rgba(70,218,244,${alpha})`;ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke();
        if(k%9===0){const t=reduce.matches?.5:(phase*2+k*.13)%1;ctx.fillStyle=active?'#c5fff0':'#79eaff';ctx.beginPath();ctx.arc(a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t,active?1.8:1.1,0,Math.PI*2);ctx.fill();}
      });
      projected.forEach(([x,y,z],i)=>{ctx.globalAlpha=.3+(z+1)*.35;ctx.fillStyle=i%7===0?'#c2fff2':'#55d9ee';ctx.beginPath();ctx.arc(x,y,(z+1)*.7+1,0,Math.PI*2);ctx.fill();});ctx.globalAlpha=1;
      const core=ctx.createRadialGradient(cx,cy,0,cx,cy,r*.24);core.addColorStop(0,'#d4ffffcc');core.addColorStop(.2,'#5df6e980');core.addColorStop(1,'#22eaff00');ctx.fillStyle=core;ctx.beginPath();ctx.arc(cx,cy,r*.24,0,Math.PI*2);ctx.fill();
    }
    if(!reduce.matches) frame=requestAnimationFrame(draw);
  }
  function wake(){if(!frame&&!document.hidden)frame=requestAnimationFrame(draw);}
  document.addEventListener('visibilitychange',()=>{if(document.hidden){cancelAnimationFrame(frame);frame=0;}else wake();});
  window.addEventListener('resize',wake);reduce.addEventListener('change',wake);
  new MutationObserver(wake).observe(document.body,{attributes:true,subtree:true,attributeFilter:['class']});
  wake();
})();
