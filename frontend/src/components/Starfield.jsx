import { useEffect, useRef } from 'react'

export default function Starfield() {
  const ref = useRef(null)

  useEffect(() => {
    const canvas = ref.current
    const ctx = canvas.getContext('2d')
    let stars = []
    let raf

    function resize() {
      canvas.width = window.innerWidth
      canvas.height = window.innerHeight
      stars = Array.from({ length: 130 }, () => ({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        r: Math.random() * 1.2 + 0.2,
        a: Math.random(),
        s: Math.random() * 0.015 + 0.003,
      }))
    }
    resize()
    window.addEventListener('resize', resize)

    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      ctx.fillStyle = '#fff'
      for (const s of stars) {
        s.a += s.s
        if (s.a > 1 || s.a < 0) s.s *= -1
        ctx.globalAlpha = Math.abs(Math.sin(s.a * 3.14)) * 0.8
        ctx.beginPath()
        ctx.arc(s.x, s.y, s.r, 0, 7)
        ctx.fill()
      }
      ctx.globalAlpha = 1
      raf = requestAnimationFrame(draw)
    }
    draw()

    return () => {
      window.removeEventListener('resize', resize)
      cancelAnimationFrame(raf)
    }
  }, [])

  return <canvas id="starfield" ref={ref} />
}
