const SHARE_BUNDLE_TYPE = 'provider-share-bundle'
const SHARE_BUNDLE_VERSION = 1
const PBKDF2_ITERATIONS = 250_000

export interface ShareBundle {
  version: 1
  type: typeof SHARE_BUNDLE_TYPE
  cipher: 'AES-GCM'
  kdf: 'PBKDF2'
  hash: 'SHA-256'
  iterations: number
  salt: string
  iv: string
  payload: string
}

function toBase64(bytes: Uint8Array): string {
  let binary = ''
  const chunkSize = 0x8000
  for (let i = 0; i < bytes.length; i += chunkSize) {
    const chunk = bytes.subarray(i, i + chunkSize)
    binary += String.fromCharCode(...chunk)
  }
  return btoa(binary)
}

function fromBase64(value: string): Uint8Array {
  const binary = atob(value)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i)
  }
  return bytes
}

async function deriveShareKey(password: string, salt: Uint8Array) {
  const material = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(password),
    { name: 'PBKDF2' },
    false,
    ['deriveKey'],
  )

  return crypto.subtle.deriveKey(
    {
      name: 'PBKDF2',
      salt,
      iterations: PBKDF2_ITERATIONS,
      hash: 'SHA-256',
    },
    material,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  )
}

export async function createShareBundle<T>(payload: T, password: string): Promise<ShareBundle> {
  if (password.trim().length < 8) {
    throw new Error('分享密码至少需要 8 位')
  }

  const salt = crypto.getRandomValues(new Uint8Array(16))
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const key = await deriveShareKey(password, salt)
  const plaintext = new TextEncoder().encode(JSON.stringify(payload))
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    plaintext,
  )

  return {
    version: SHARE_BUNDLE_VERSION,
    type: SHARE_BUNDLE_TYPE,
    cipher: 'AES-GCM',
    kdf: 'PBKDF2',
    hash: 'SHA-256',
    iterations: PBKDF2_ITERATIONS,
    salt: toBase64(salt),
    iv: toBase64(iv),
    payload: toBase64(new Uint8Array(ciphertext)),
  }
}

export async function readShareBundle<T>(input: string, password: string): Promise<T> {
  if (password.trim().length < 8) {
    throw new Error('分享密码至少需要 8 位')
  }

  let bundle: ShareBundle
  try {
    bundle = JSON.parse(input) as ShareBundle
  } catch {
    throw new Error('分享包不是有效的 JSON')
  }

  if (
    bundle.version !== SHARE_BUNDLE_VERSION
    || bundle.type !== SHARE_BUNDLE_TYPE
    || bundle.cipher !== 'AES-GCM'
    || bundle.kdf !== 'PBKDF2'
  ) {
    throw new Error('分享包格式不受支持')
  }

  const salt = fromBase64(bundle.salt)
  const iv = fromBase64(bundle.iv)
  const ciphertext = fromBase64(bundle.payload)
  const key = await deriveShareKey(password, salt)

  let plaintext: ArrayBuffer
  try {
    plaintext = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv },
      key,
      ciphertext,
    )
  } catch {
    throw new Error('解密失败，请检查分享密码是否正确')
  }

  try {
    return JSON.parse(new TextDecoder().decode(plaintext)) as T
  } catch {
    throw new Error('分享包内容损坏，无法解析')
  }
}
