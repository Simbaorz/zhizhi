const SHA256_BLOCK_SIZE = 64;
const SHA256_DIGEST_SIZE = 32;
const SHA256_INITIAL_HASH = [
  0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c,
  0x1f83d9ab, 0x5be0cd19,
];
const SHA256_ROUND_CONSTANTS = [
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
  0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
  0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
  0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
  0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
  0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];

interface RsaPublicKey {
  modulus: bigint;
  exponent: bigint;
  sizeBytes: number;
}

interface DerReader {
  bytes: Uint8Array;
  offset: number;
}

interface DerNode {
  tag: number;
  value: Uint8Array;
}

export function pemToDer(pem: string): Uint8Array {
  const base64 = pem
    .replace("-----BEGIN PUBLIC KEY-----", "")
    .replace("-----END PUBLIC KEY-----", "")
    .replace(/\s/g, "");
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

export function rsaOaepSha256EncryptToBase64(message: string, spkiDer: Uint8Array): string {
  const publicKey = parseSpkiPublicKey(spkiDer);
  const encoded = new TextEncoder().encode(message);
  const encrypted = rsaOaepSha256Encrypt(encoded, publicKey);
  return bytesToBase64(encrypted);
}

function parseSpkiPublicKey(spkiDer: Uint8Array): RsaPublicKey {
  const root = readDerNode({ bytes: spkiDer, offset: 0 }, 0x30);
  const rootReader = { bytes: root.value, offset: 0 };
  readDerNode(rootReader, 0x30);
  const bitString = readDerNode(rootReader, 0x03).value;
  if (bitString.length < 2 || bitString[0] !== 0) {
    throw new Error("无效的 RSA 公钥。");
  }
  const rsaKeyNode = readDerNode({ bytes: bitString.slice(1), offset: 0 }, 0x30);
  const keyReader = { bytes: rsaKeyNode.value, offset: 0 };
  const modulusBytes = trimIntegerBytes(readDerNode(keyReader, 0x02).value);
  const exponentBytes = trimIntegerBytes(readDerNode(keyReader, 0x02).value);
  return {
    modulus: bytesToBigInt(modulusBytes),
    exponent: bytesToBigInt(exponentBytes),
    sizeBytes: modulusBytes.length,
  };
}

function readDerNode(reader: DerReader, expectedTag: number): DerNode {
  if (reader.offset >= reader.bytes.length) {
    throw new Error("无效的 DER 数据。");
  }
  const tag = reader.bytes[reader.offset];
  reader.offset += 1;
  if (tag !== expectedTag) {
    throw new Error("无效的 DER 数据。");
  }
  const length = readDerLength(reader);
  const end = reader.offset + length;
  if (end > reader.bytes.length) {
    throw new Error("无效的 DER 数据。");
  }
  const value = reader.bytes.slice(reader.offset, end);
  reader.offset = end;
  return { tag, value };
}

function readDerLength(reader: DerReader): number {
  const first = reader.bytes[reader.offset];
  reader.offset += 1;
  if ((first & 0x80) === 0) {
    return first;
  }
  const count = first & 0x7f;
  if (count === 0 || count > 4 || reader.offset + count > reader.bytes.length) {
    throw new Error("无效的 DER 长度。");
  }
  let length = 0;
  for (let index = 0; index < count; index += 1) {
    length = (length << 8) | reader.bytes[reader.offset];
    reader.offset += 1;
  }
  return length;
}

function rsaOaepSha256Encrypt(message: Uint8Array, publicKey: RsaPublicKey): Uint8Array {
  const encodedMessage = oaepEncode(message, publicKey.sizeBytes);
  const messageNumber = bytesToBigInt(encodedMessage);
  if (messageNumber >= publicKey.modulus) {
    throw new Error("密码加密失败。");
  }
  const encrypted = modPow(messageNumber, publicKey.exponent, publicKey.modulus);
  return bigIntToFixedBytes(encrypted, publicKey.sizeBytes);
}

function oaepEncode(message: Uint8Array, keySize: number): Uint8Array {
  const hLen = SHA256_DIGEST_SIZE;
  if (message.length > keySize - 2 * hLen - 2) {
    throw new Error("密码过长，无法加密。");
  }
  const labelHash = sha256(new Uint8Array());
  const ps = new Uint8Array(keySize - message.length - 2 * hLen - 2);
  const db = concatBytes(labelHash, ps, new Uint8Array([0x01]), message);
  const seed = randomBytes(hLen);
  const maskedDb = xorBytes(db, mgf1(seed, keySize - hLen - 1));
  const maskedSeed = xorBytes(seed, mgf1(maskedDb, hLen));
  return concatBytes(new Uint8Array([0x00]), maskedSeed, maskedDb);
}

function mgf1(seed: Uint8Array, length: number): Uint8Array {
  const output = new Uint8Array(length);
  let offset = 0;
  let counter = 0;
  while (offset < length) {
    const counterBytes = new Uint8Array([
      (counter >>> 24) & 0xff,
      (counter >>> 16) & 0xff,
      (counter >>> 8) & 0xff,
      counter & 0xff,
    ]);
    const digest = sha256(concatBytes(seed, counterBytes));
    const chunk = digest.slice(0, Math.min(digest.length, length - offset));
    output.set(chunk, offset);
    offset += chunk.length;
    counter += 1;
  }
  return output;
}

function sha256(message: Uint8Array): Uint8Array {
  const bitLength = message.length * 8;
  const paddedLength = Math.ceil((message.length + 9) / SHA256_BLOCK_SIZE) * SHA256_BLOCK_SIZE;
  const padded = new Uint8Array(paddedLength);
  padded.set(message);
  padded[message.length] = 0x80;
  const high = Math.floor(bitLength / 0x100000000);
  const low = bitLength >>> 0;
  writeUint32(padded, padded.length - 8, high);
  writeUint32(padded, padded.length - 4, low);

  const hash = SHA256_INITIAL_HASH.slice();
  const words = new Array<number>(64).fill(0);
  for (let chunkOffset = 0; chunkOffset < padded.length; chunkOffset += SHA256_BLOCK_SIZE) {
    for (let index = 0; index < 16; index += 1) {
      words[index] = readUint32(padded, chunkOffset + index * 4);
    }
    for (let index = 16; index < 64; index += 1) {
      const s0 =
        rotateRight(words[index - 15], 7) ^
        rotateRight(words[index - 15], 18) ^
        (words[index - 15] >>> 3);
      const s1 =
        rotateRight(words[index - 2], 17) ^
        rotateRight(words[index - 2], 19) ^
        (words[index - 2] >>> 10);
      words[index] = (words[index - 16] + s0 + words[index - 7] + s1) >>> 0;
    }
    let [a, b, c, d, e, f, g, h] = hash;
    for (let index = 0; index < 64; index += 1) {
      const s1 = rotateRight(e, 6) ^ rotateRight(e, 11) ^ rotateRight(e, 25);
      const ch = (e & f) ^ (~e & g);
      const temp1 = (h + s1 + ch + SHA256_ROUND_CONSTANTS[index] + words[index]) >>> 0;
      const s0 = rotateRight(a, 2) ^ rotateRight(a, 13) ^ rotateRight(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (s0 + maj) >>> 0;
      h = g;
      g = f;
      f = e;
      e = (d + temp1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (temp1 + temp2) >>> 0;
    }
    hash[0] = (hash[0] + a) >>> 0;
    hash[1] = (hash[1] + b) >>> 0;
    hash[2] = (hash[2] + c) >>> 0;
    hash[3] = (hash[3] + d) >>> 0;
    hash[4] = (hash[4] + e) >>> 0;
    hash[5] = (hash[5] + f) >>> 0;
    hash[6] = (hash[6] + g) >>> 0;
    hash[7] = (hash[7] + h) >>> 0;
  }
  const digest = new Uint8Array(SHA256_DIGEST_SIZE);
  hash.forEach((word, index) => writeUint32(digest, index * 4, word));
  return digest;
}

function randomBytes(length: number): Uint8Array {
  const bytes = new Uint8Array(length);
  const cryptoApi = globalThis.crypto;
  if (!cryptoApi?.getRandomValues) {
    throw new Error("当前浏览器不支持密码加密所需的随机数能力。");
  }
  cryptoApi.getRandomValues(bytes);
  return bytes;
}

function modPow(base: bigint, exponent: bigint, modulus: bigint): bigint {
  let result = 1n;
  let currentBase = base % modulus;
  let currentExponent = exponent;
  while (currentExponent > 0n) {
    if ((currentExponent & 1n) === 1n) {
      result = (result * currentBase) % modulus;
    }
    currentExponent >>= 1n;
    currentBase = (currentBase * currentBase) % modulus;
  }
  return result;
}

function bytesToBigInt(bytes: Uint8Array): bigint {
  let value = 0n;
  for (const byte of bytes) {
    value = (value << 8n) | BigInt(byte);
  }
  return value;
}

function bigIntToFixedBytes(value: bigint, size: number): Uint8Array {
  const bytes = new Uint8Array(size);
  let remaining = value;
  for (let index = size - 1; index >= 0; index -= 1) {
    bytes[index] = Number(remaining & 0xffn);
    remaining >>= 8n;
  }
  return bytes;
}

function trimIntegerBytes(bytes: Uint8Array): Uint8Array {
  let offset = 0;
  while (offset < bytes.length - 1 && bytes[offset] === 0) {
    offset += 1;
  }
  return bytes.slice(offset);
}

function concatBytes(...parts: Uint8Array[]): Uint8Array {
  const length = parts.reduce((total, part) => total + part.length, 0);
  const output = new Uint8Array(length);
  let offset = 0;
  for (const part of parts) {
    output.set(part, offset);
    offset += part.length;
  }
  return output;
}

function xorBytes(left: Uint8Array, right: Uint8Array): Uint8Array {
  const output = new Uint8Array(left.length);
  for (let index = 0; index < left.length; index += 1) {
    output[index] = left[index] ^ right[index];
  }
  return output;
}

function rotateRight(value: number, bits: number): number {
  return (value >>> bits) | (value << (32 - bits));
}

function readUint32(bytes: Uint8Array, offset: number): number {
  return (
    ((bytes[offset] << 24) |
      (bytes[offset + 1] << 16) |
      (bytes[offset + 2] << 8) |
      bytes[offset + 3]) >>>
    0
  );
}

function writeUint32(bytes: Uint8Array, offset: number, value: number): void {
  bytes[offset] = (value >>> 24) & 0xff;
  bytes[offset + 1] = (value >>> 16) & 0xff;
  bytes[offset + 2] = (value >>> 8) & 0xff;
  bytes[offset + 3] = value & 0xff;
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}
