import { useSyncExternalStore } from 'react'

export type Animal = 'corgi' | 'capybara'

const KEY = 'answerAnimal'
const CHANGED = 'animal:changed'

function read(): Animal {
  try {
    return localStorage.getItem(KEY) === 'corgi' ? 'corgi' : 'capybara'
  } catch {
    return 'capybara'
  }
}

export function setAnimal(animal: Animal) {
  try {
    localStorage.setItem(KEY, animal)
  } catch {
    /* the choice just won't be remembered */
  }
  window.dispatchEvent(new Event(CHANGED))
}

function subscribe(callback: () => void) {
  window.addEventListener(CHANGED, callback)
  return () => window.removeEventListener(CHANGED, callback)
}

/** Which animal answers (its face is the icon next to every answer). */
export function useAnimal(): Animal {
  return useSyncExternalStore(subscribe, read, () => 'capybara')
}
