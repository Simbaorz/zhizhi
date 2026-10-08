import { pemToDer, rsaOaepSha256EncryptToBase64 } from "./rsaOaepFallback";

export interface PasswordKey {
  algorithm: string;
  key_id: string;
  public_key_pem: string;
}

export async function encryptPasswords(key: PasswordKey, passwords: string[]): Promise<string[]> {
  if (key.algorithm !== "RSA-OAEP-256" || !/^[a-f0-9]{16}$/.test(key.key_id)) {
    throw new Error("不支持的密码加密配置");
  }
  const der = pemToDer(key.public_key_pem);
  if (!globalThis.crypto?.subtle) {
    return passwords.map((password) => `${key.key_id}.${rsaOaepSha256EncryptToBase64(password, der)}`);
  }
  const publicKey = await crypto.subtle.importKey(
    "spki", der, { name: "RSA-OAEP", hash: "SHA-256" }, false, ["encrypt"],
  );
  return Promise.all(passwords.map(async (password) => {
    const ciphertext = await crypto.subtle.encrypt(
      { name: "RSA-OAEP" }, publicKey, new TextEncoder().encode(password),
    );
    const bytes = new Uint8Array(ciphertext);
    let binary = "";
    for (const byte of bytes) binary += String.fromCharCode(byte);
    return `${key.key_id}.${btoa(binary)}`;
  }));
}
