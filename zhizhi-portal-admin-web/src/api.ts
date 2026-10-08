import { encryptPasswords, type PasswordKey } from "./passwordCrypto";
import { accountPayload } from "./accountPayload";
export interface Binding {id?:string;tenant_id:string;organization_unit_id:string}
export interface Account {id:string;username:string;display_name:string;email:string;active:boolean;scopes:Binding[]}
export interface Scope {tenant_id:string;organization_unit_id:string;label:string;tenant_name:string}
export interface Tenant {id:string;tenant_name:string;tenant_code:string}
export interface Admin {id:string;username:string;display_name:string}
export interface AccountInput {username?:string;display_name:string;email:string;active:boolean;scopes:Binding[];password?:string}
export class ApiError extends Error {constructor(message:string,readonly status:number){super(message);}}
export async function request<T>(path:string, method="GET", body?:unknown):Promise<T> {
  const headers = new Headers({Accept:"application/json"});
  if(body!==undefined) headers.set("Content-Type","application/json");
  if(method!=="GET") headers.set("x-csrf-token",decodeURIComponent(document.cookie.match(/(?:^|; )zhizhi_portal_admin_csrf=([^;]*)/)?.[1] || ""));
  const response=await fetch(path,{method,headers,body:body===undefined?undefined:JSON.stringify(body)});
  if(!response.ok){const payload=await response.json().catch(()=>({}));throw new ApiError(typeof payload.detail==="string"?payload.detail:"请求失败，请重试。",response.status);}
  return response.json() as Promise<T>;
}
async function passwordKey(){return request<PasswordKey>("/api/admin/auth/password-key");}
export async function login(username:string,password:string){const [encrypted_password]=await encryptPasswords(await passwordKey(),[password]);return request<Admin>("/api/admin/auth/login","POST",{username,encrypted_password});}
export async function saveAccount(input:AccountInput,id?:string){const encrypted_password=input.password?(await encryptPasswords(await passwordKey(),[input.password]))[0]:undefined;return request<Account>(id?`/api/admin/accounts/${id}`:"/api/admin/accounts",id?"PATCH":"POST",accountPayload(input,encrypted_password));}
