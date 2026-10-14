const V='4nt-v1',SHELL=['/offline','/static/icons/logo-small.png','/static/icons/icon-192.png'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(V).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting()));});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(k=>Promise.all(k.filter(x=>x!==V).map(x=>caches.delete(x)))).then(()=>self.clients.claim()));});
self.addEventListener('fetch',e=>{
  const r=e.request,u=new URL(r.url);
  if(r.method!=='GET'||u.origin!==location.origin)return;
  if(u.pathname.startsWith('/static/icons/')){e.respondWith(caches.match(r).then(m=>m||fetch(r)));return;}
  // pages are never cached (they hold private attendance data); show offline page if the network fails
  if(r.mode==='navigate'){e.respondWith(fetch(r).catch(()=>caches.match('/offline')));}
});
