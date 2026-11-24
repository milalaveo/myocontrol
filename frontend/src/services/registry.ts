import type { Collection, RegistryDetail, RegistryPage } from '../types/cloud'
import { requestJson } from './http'

export const PAGE_SIZE = 25

export function listRegistry(collection: Collection, offset: number, signal: AbortSignal) {
  return requestJson<RegistryPage>(`cloud/v1/${collection}?limit=${PAGE_SIZE}&offset=${offset}`, {
    signal,
  })
}

export function getRegistryDetail(collection: Collection, id: string, signal: AbortSignal) {
  return requestJson<RegistryDetail>(`cloud/v1/${collection}/${encodeURIComponent(id)}`, {
    signal,
  })
}
