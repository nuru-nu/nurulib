import { h, ui, u, colors, Lines } from './util.js'

export const Monitor = (output, { presets }) => {

  let signals = null

  const width=600, height=128, speed=3, lw=1

  presets = presets || {}
  presets.none = new Set()
  presets.all = new Set()
  let preset = presets.default || presets.all

  const disp = h.div({class: 'flex'}).of(
    h.div().of(
      h.canvas('graph', {width, height}),
      h.br(),
      h.div('lines', {style: `width: ${width}px`}).of(
        h.select('preset').of(
          Object.keys(presets).map(preset => (
            h.option({value: preset}).of(preset)))
        ),
      ),
      h.br(),
      h.div('text_sigs'),
    ),
  ).into(output).els

  const lines = Lines(disp.lines)

  disp.preset.addEventListener('change', () => {
    preset = presets[disp.preset.value]
    lines.set(preset)
  })

  const ctx = disp.graph.getContext('2d')

  let t=-1, lastys={}
  const nolines = new Set(['logmel', 'mfccs', 't', 'signalin'])
  const text_sigs = new Set(['state', 'position'])
  function listener(data) {
    signals = data
    t++
    if (signals.state.indexOf('frozen') !== -1) {
      disp.text_sigs.textContent = signals.state
      return
    }
    const img = ctx.getImageData(speed, 0, width - speed - 1, height)
    ctx.putImageData(img, 0, 0);
    ctx.fillStyle = '#000'
    ctx.fillRect(width - speed - 1, 0, speed, height)

    if (signals.hasOwnProperty('logmel')) {
      signals.logmel.forEach((value, i) => {
        value = (value + 5) / 10
        value = Math.min(1, Math.max(0, value))
        ctx.fillStyle = colors.greens[Math.floor(255 * value)]
        ctx.fillRect(width - speed - 1, height - i * 2, speed, 2)
      })
    }

    let text = ''
    u.sorted(Object.keys(signals)).forEach(sig => {
      if (text_sigs.has(sig)) {
        text += `${sig}=${signals[sig]} `
        return
      }
      if (nolines.has(sig)) {
        return
      }
      presets.all.add(sig)
      const color = lines.get(sig, t, preset)
      if (color) {
        const y = Math.floor((height - 1) * (1 - signals[sig]))
        const lasty = lastys.hasOwnProperty(sig) ? lastys[sig] : y
        ctx.fillStyle = color
        ctx.fillRect(
          width - speed - 1, Math.min(y, lasty),
          Math.min(lw, speed), Math.abs(y - lasty) + lw)
        ctx.fillRect(
          width - speed - 1, y,
          speed, lw)
        lastys[sig] = y
      }
    })
    disp.text_sigs.textContent = text
  }

  return {
    listener,
  }
}

export const Dump = output => {
  const disp = h.div().of(
    ui.h(
      h.button('dump').of('dump'),
      h.button('clear').of('clear'),
    ),
    h.pre('output'),
  ).into(output).els

  disp.dump.addEventListener('click', () => {
    disp.output.textContent = ''
    u.sorted(Object.entries(signals)).map(([k, v]) => {
      if (Array.isArray(v) && v.length && 'number' === typeof v[0]) {
        v = `[${v.map(x => x.toFixed(3)).join(',')}]`
      } else if ('object' === typeof v) {
        v = JSON.stringify(v)
      }
      disp.output.textContent += `${k} = ${v}\n`
    })
  })

  disp.clear.addEventListener('click', () => {
    disp.output.textContent = ''
  })

  let signals = null
  function listener(data) {
    signals = data
  }

  return {
    listener,
  }
}
