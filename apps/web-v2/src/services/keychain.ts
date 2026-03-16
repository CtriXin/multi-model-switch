/**
 * Secure API key storage using Web Crypto API + IndexedDB.
 * Keys are encrypted with AES-256-GCM before storage.
 * The master key is a non-extractable CryptoKey in IndexedDB.
 */

const DB_NAME = 'mms-keychain'
const DB_VERSION = 1
const MASTER_KEY_STORE = 'master-key'
const CREDENTIALS_STORE = 'credentials'

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(MASTER_KEY_STORE)) {
        db.createObjectStore(MASTER_KEY_STORE)
      }
      if (!db.objectStoreNames.contains(CREDENTIALS_STORE)) {
        db.createObjectStore(CREDENTIALS_STORE)
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

function idbGet<T>(db: IDBDatabase, store: string, key: string): Promise<T | undefined> {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, 'readonly')
    const req = tx.objectStore(store).get(key)
    req.onsuccess = () => resolve(req.result as T | undefined)
    req.onerror = () => reject(req.error)
  })
}

function idbPut(db: IDBDatabase, store: string, key: string, value: unknown): Promise<void> {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, 'readwrite')
    tx.objectStore(store).put(value, key)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

function idbDelete(db: IDBDatabase, store: string, key: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, 'readwrite')
    tx.objectStore(store).delete(key)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

function idbClear(db: IDBDatabase, store: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, 'readwrite')
    tx.objectStore(store).clear()
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

function idbAllKeys(db: IDBDatabase, store: string): Promise<string[]> {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, 'readonly')
    const req = tx.objectStore(store).getAllKeys()
    req.onsuccess = () => resolve(req.result as string[])
    req.onerror = () => reject(req.error)
  })
}

async function getMasterKey(): Promise<CryptoKey> {
  const db = await openDB()
  const existing = await idbGet<CryptoKey>(db, MASTER_KEY_STORE, 'master')
  if (existing) return existing

  const key = await crypto.subtle.generateKey(
    { name: 'AES-GCM', length: 256 },
    false, // non-extractable
    ['encrypt', 'decrypt'],
  )
  await idbPut(db, MASTER_KEY_STORE, 'master', key)
  return key
}

interface EncryptedBlob {
  iv: Uint8Array
  ciphertext: ArrayBuffer
}

async function encrypt(plaintext: string): Promise<EncryptedBlob> {
  const key = await getMasterKey()
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const encoded = new TextEncoder().encode(plaintext)
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    encoded,
  )
  return { iv, ciphertext }
}

async function decrypt(blob: EncryptedBlob): Promise<string> {
  const key = await getMasterKey()
  const plainBuffer = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: blob.iv },
    key,
    blob.ciphertext,
  )
  return new TextDecoder().decode(plainBuffer)
}

export async function saveApiKey(providerId: string, apiKey: string): Promise<void> {
  const db = await openDB()
  const blob = await encrypt(apiKey)
  await idbPut(db, CREDENTIALS_STORE, providerId, blob)
}

export async function getApiKey(providerId: string): Promise<string | null> {
  const db = await openDB()
  const blob = await idbGet<EncryptedBlob>(db, CREDENTIALS_STORE, providerId)
  if (!blob) return null
  return decrypt(blob)
}

export async function deleteApiKey(providerId: string): Promise<void> {
  const db = await openDB()
  await idbDelete(db, CREDENTIALS_STORE, providerId)
}

export async function hasApiKey(providerId: string): Promise<boolean> {
  const db = await openDB()
  const blob = await idbGet(db, CREDENTIALS_STORE, providerId)
  return blob !== undefined
}

export async function listCredentialIds(): Promise<string[]> {
  const db = await openDB()
  return idbAllKeys(db, CREDENTIALS_STORE)
}

export async function listProviderIds(): Promise<string[]> {
  return listCredentialIds()
}

export async function clearAll(): Promise<void> {
  const db = await openDB()
  await idbClear(db, CREDENTIALS_STORE)
}

/** Mask an API key for display: "sk-or-v1-xxxx...abcd" → "sk-or****abcd" */
export function maskKey(key: string): string {
  if (key.length <= 8) return '****'
  return key.slice(0, 4) + '****' + key.slice(-4)
}
