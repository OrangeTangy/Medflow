// Cache the static shell only. Attendance, transcripts, and API responses are never cached.
self.addEventListener('install',()=>self.skipWaiting());
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
self.addEventListener('fetch',event=>{if(event.request.mode==='navigate')event.respondWith(fetch(event.request).catch(()=>new Response('<h1>Medflow is offline</h1><p>Reconnect to securely view your workspace. Sensitive records are not stored offline.</p>',{headers:{'Content-Type':'text/html'}})));});
