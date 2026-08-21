import { useEffect, useState } from 'react'

export default function Counter({ target = 0 }) {
  const [value, setValue] = useState(0)

  useEffect(() => {
    let cur = 0
    const step = Math.max(1, target / 60)
    const t = setInterval(() => {
      cur += step
      if (cur >= target) {
        cur = target
        clearInterval(t)
      }
      setValue(Math.floor(cur))
    }, 16)
    return () => clearInterval(t)
  }, [target])

  return <>{value.toLocaleString()}</>
}
