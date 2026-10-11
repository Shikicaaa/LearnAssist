import { useSyncExternalStore } from 'react'

/** The composer tells the room that the student is typing; the room never imports the composer. */
const TYPING_EVENT = 'lofi:typing'

export function signalTyping() {
  window.dispatchEvent(new Event(TYPING_EVENT))
}

export function onTyping(handler: () => void): () => void {
  window.addEventListener(TYPING_EVENT, handler)
  return () => window.removeEventListener(TYPING_EVENT, handler)
}

// --- the on/off setting ---------------------------------------------------------------------

const KEY = 'lofiRoom'
const CHANGED = 'lofi:setting'

function read(): boolean {
  try {
    return localStorage.getItem(KEY) !== 'off' // on unless the student switched it off
  } catch {
    return true
  }
}

export function setRoomEnabled(enabled: boolean) {
  try {
    localStorage.setItem(KEY, enabled ? 'on' : 'off')
  } catch {
    /* the choice just won't be remembered */
  }
  window.dispatchEvent(new Event(CHANGED))
}

function subscribe(callback: () => void) {
  window.addEventListener(CHANGED, callback)
  return () => window.removeEventListener(CHANGED, callback)
}

export function useRoomEnabled(): boolean {
  return useSyncExternalStore(subscribe, read, () => true)
}
