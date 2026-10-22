// Local-only QA server. Never included in the deployment Worker or Python API.
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {DatabaseSync} from 'node:sqlite';
import {api} from '../worker/api.mjs';
const sqlite=new DatabaseSync('/tmp/medflow-preview.sqlite');
sqlite.exec('CREATE TABLE IF NOT EXISTS sandbox_workspaces (owner TEXT PRIMARY KEY,data TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1)');
const DB={prepare(sql){let params=[];return {bind(...args){params=args;return this},async first(){return sqlite.prepare(sql).get(...params)},async run(){const result=sqlite.prepare(sql).run(...params);return {meta:{changes:result.changes}}}}}};
const types={html:'text/html',js:'text/javascript',css:'text/css',svg:'image/svg+xml',webmanifest:'application/manifest+json'};
createServer(async(req,res)=>{try{
 const url=new URL(req.url,'http://127.0.0.1:4173');let response;
 if(url.pathname.startsWith('/api/')){const chunks=[];for await(const c of req)chunks.push(c);const body=Buffer.concat(chunks);const request=new Request(url,{method:req.method,headers:{...req.headers,'oai-authenticated-user-id':'local-qa-owner'},body:['GET','HEAD'].includes(req.method)?undefined:body});response=await api(request,{DB})}
 else{const path=url.pathname==='/'?'index.html':url.pathname.slice(1);if(path.includes('..'))throw Error('Invalid path');const bytes=await readFile('out/'+path);response=new Response(bytes,{headers:{'content-type':types[path.split('.').pop()]||'application/octet-stream'}})}
 res.writeHead(response.status,Object.fromEntries(response.headers));res.end(Buffer.from(await response.arrayBuffer()));
 }catch{res.writeHead(404);res.end('Not found')}}).listen(4173,'127.0.0.1',()=>console.log('Local QA: http://127.0.0.1:4173'));
