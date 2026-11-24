import type { Collection, RegistryDetail, RegistryPage } from '../types/cloud'
import { requestJson } from './http'

export const PAGE_SIZE = 25

export function listRegistry(
  collection: Collection,
  offset: number,
  token: string,
  signal: AbortSignal,
) {
  return requestJson<RegistryPage>(`cloud/v1/${collection}?limit=${PAGE_SIZE}&offset=${offset}`, {
    token,
    signal,
  })
}

export function getRegistryDetail(
  collection: Collection,
  id: string,
  token: string,
  signal: AbortSignal,
) {
  return requestJson<RegistryDetail>(`cloud/v1/${collection}/${encodeURIComponent(id)}`, {
    token,
    signal,
  })
}
