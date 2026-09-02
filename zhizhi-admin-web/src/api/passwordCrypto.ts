import { fetchJson } from "@/api/http";
import { pemToDer, rsaOaepSha256EncryptToBase64 } from "@/api/rsaOaepFallback";

interface PasswordKeyResponse {
  algorithm: string;
  key_id: string;
  public_key_pem: string;
}

export async function encryptAdminPassword(password: string): Promise<string> {
  const payload = await getPasswordKey();
  if (payload.algorithm !== "RSA-OAEP-256") {
    throw new Error("不支持的密码加密算法。");
  }
  const publicKeyDer = pemToDer(payload.public_key_pem);
  if (!globalThis.crypto?.subtle) {
    return withKeyId(
      payload.key_id,
      rsaOaepSha256EncryptToBase64(password, publicKeyDer),
    );
  }
  const publicKey = await importPublicKey(publicKeyDer);
  const ciphertext = await crypto.subtle.encrypt(
    { name: "RSA-OAEP" },
    publicKey,
    new TextEncoder().encode(password),
  );
  return withKeyId(payload.key_id, arrayBufferToBase64(ciphertext));
}

function withKeyId(keyId: string, ciphertext: string): string {
  if (!/^[a-f0-9]{16}$/.test(keyId)) {
    throw new Error("无效的密码加密密钥标识。");
  }
  return `${keyId}.${ciphertext}`;
}

async function getPasswordKey(): Promise<PasswordKeyResponse> {
  return fetchJson<PasswordKeyResponse>("/api/admin/auth/password-key");
}

async function importPublicKey(der: Uint8Array): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "spki",
    der,
    {
      name: "RSA-OAEP",
      hash: "SHA-256",
    },
    false,
    ["encrypt"],
  );
}

function arrayBufferToBase64(value: ArrayBuffer): string {
  const bytes = new Uint8Array(value);
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}
