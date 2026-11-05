const IMAGE_TYPES={"image/jpeg":"jpg","image/png":"png","image/webp":"webp","image/tiff":"tif"};
const MAX_BYTES=15*1024*1024;
const encoder=new TextEncoder();
const json=(data,status=200,headers={})=>new Response(JSON.stringify(data),{status,headers:{"content-type":"application/json; charset=utf-8",...headers}});
const hex=buffer=>[...new Uint8Array(buffer)].map(x=>x.toString(16).padStart(2,"0")).join("");
const randomHex=bytes=>{const value=new Uint8Array(bytes);crypto.getRandomValues(value);return hex(value)};
const hash=value=>crypto.subtle.digest("SHA-256",encoder.encode(value)).then(hex);
const clean=(value,max=1200)=>String(value||"").trim().slice(0,max);

function cors(request,env){
  const origin=request.headers.get("origin")||"";
  return origin===env.ALLOWED_ORIGIN?{"access-control-allow-origin":origin,"vary":"Origin"}:{};
}
async function record(env,id){return env.UPLOADS.get(`records/${id}.json`,"json")}
async function save(env,data){await env.UPLOADS.put(`records/${data.id}.json`,JSON.stringify(data))}
const decodePart=value=>JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(value.replace(/-/g,"+").replace(/_/g,"/").padEnd(Math.ceil(value.length/4)*4,"=")),c=>c.charCodeAt(0))));
async function authorize(request,env){
  const token=(request.headers.get("authorization")||"").replace(/^Bearer\s+/i,"");
  const parts=token.split(".");if(parts.length!==3)return false;
  const header=decodePart(parts[0]),claims=decodePart(parts[1]);
  if(header.alg!=="RS256"||claims.iss!=="https://token.actions.githubusercontent.com"||claims.aud!==env.OIDC_AUDIENCE||claims.repository!==env.GITHUB_REPOSITORY||Number(claims.exp)*1000<Date.now())return false;
  const discovery=await fetch("https://token.actions.githubusercontent.com/.well-known/openid-configuration").then(r=>r.json()),jwks=await fetch(discovery.jwks_uri).then(r=>r.json()),jwk=jwks.keys.find(key=>key.kid===header.kid);if(!jwk)return false;
  const key=await crypto.subtle.importKey("jwk",jwk,{name:"RSASSA-PKCS1-v1_5",hash:"SHA-256"},false,["verify"]),signature=Uint8Array.from(atob(parts[2].replace(/-/g,"+").replace(/_/g,"/").padEnd(Math.ceil(parts[2].length/4)*4,"=")),c=>c.charCodeAt(0));
  return crypto.subtle.verify("RSASSA-PKCS1-v1_5",key,signature,encoder.encode(`${parts[0]}.${parts[1]}`));
}
async function owner(request,data){const token=new URL(request.url).searchParams.get("token")||request.headers.get("x-edit-token")||"";return token&&await hash(token)===data.edit_token_hash}

export default {async fetch(request,env){
  const url=new URL(request.url),headers=cors(request,env);
  if(request.method==="OPTIONS")return new Response(null,{status:204,headers:{...headers,"access-control-allow-methods":"GET,POST,PATCH,OPTIONS","access-control-allow-headers":"content-type,authorization,x-edit-token"}});
  try{
    if(request.method==="POST"&&url.pathname==="/api/uploads"){
      const ip=request.headers.get("cf-connecting-ip")||"unknown",hour=new Date().toISOString().slice(0,13),ipHash=await hash(ip),rate=await env.UPLOADS.list({prefix:`rate/${ipHash}/${hour}/`,limit:6});
      if(rate.keys.length>=5)return json({error:"上传过于频繁，请一小时后再试。"},429,headers);
      const form=await request.formData(),file=form.get("image");
      if(!(file instanceof File)||!IMAGE_TYPES[file.type])return json({error:"请选择 JPG、PNG、WebP 或 TIFF 图片。"},400,headers);
      if(file.size>MAX_BYTES)return json({error:"图片不能超过 15 MB。"},413,headers);
      const id=`anon-${Date.now().toString(36)}-${randomHex(4)}`,token=randomHex(24),ext=IMAGE_TYPES[file.type],now=new Date().toISOString();
      await env.UPLOADS.put(`images/${id}.${ext}`,await file.arrayBuffer());
      const data={id,image_key:`images/${id}.${ext}`,content_type:file.type,title:clean(form.get("title"),160)||"待补充标题",why:clean(form.get("why"))||"快速上传，推荐理由待补充。",usage:clean(form.get("usage"))||"未来用途待补充。",contributor_name:clean(form.get("contributor_name"),120)||"匿名投稿者",rating:Math.max(1,Math.min(5,Number(form.get("rating"))||5)),edit_token_hash:await hash(token),created_at:now,updated_at:now,synced_at:null};
      await save(env,data);await env.UPLOADS.put(`rate/${ipHash}/${hour}/${id}`,"1");
      return json({id,token,manage_url:`${env.ALLOWED_ORIGIN}/scientific-figure-atlas/manage-upload.html?id=${id}&token=${token}`},201,headers);
    }
    const match=url.pathname.match(/^\/api\/uploads\/(anon-[a-z0-9-]+)$/);
    if(match){const data=await record(env,match[1]);if(!data)return json({error:"投稿不存在。"},404,headers);if(!await owner(request,data))return json({error:"管理链接无效。"},403,headers);
      if(request.method==="GET")return json({id:data.id,title:data.title,why:data.why,usage:data.usage,contributor_name:data.contributor_name,rating:data.rating,updated_at:data.updated_at,synced_at:data.synced_at},200,headers);
      if(request.method==="PATCH"){const body=await request.json();for(const key of ["title","why","usage","contributor_name"])if(key in body)data[key]=clean(body[key],key==="title"?160:1200);if("rating" in body)data.rating=Math.max(1,Math.min(5,Number(body.rating)||5));data.updated_at=new Date().toISOString();await save(env,data);return json({ok:true},200,headers)}
    }
    const image=url.pathname.match(/^\/files\/(anon-[a-z0-9-]+)$/);
    if(image&&request.method==="GET"){const data=await record(env,image[1]);if(!data)return new Response("Not found",{status:404});const object=await env.UPLOADS.get(data.image_key,"arrayBuffer");if(!object)return new Response("Not found",{status:404});return new Response(object,{headers:{"content-type":data.content_type,"cache-control":"public, max-age=3600"}})}
    if(url.pathname==="/api/sync/pending"&&request.method==="GET"){if(!await authorize(request,env))return json({error:"Unauthorized"},401);const listed=await env.UPLOADS.list({prefix:"records/",limit:100});const items=[];for(const item of listed.keys){const data=await env.UPLOADS.get(item.name,"json");if(!data.synced_at||data.updated_at>data.synced_at)items.push({...data,edit_token_hash:undefined,image_url:`${url.origin}/files/${data.id}`})}return json(items)}
    if(url.pathname==="/api/sync/complete"&&request.method==="POST"){if(!await authorize(request,env))return json({error:"Unauthorized"},401);const {ids}=await request.json();for(const id of ids||[]){const data=await record(env,id);if(data){data.synced_at=new Date().toISOString();await env.UPLOADS.delete(data.image_key);await save(env,data)}}return json({ok:true})}
    return json({service:"Figure Atlas anonymous upload","ok":true},200,headers);
  }catch(error){return json({error:"服务暂时不可用。",detail:String(error?.message||error)},500,headers)}
}};
