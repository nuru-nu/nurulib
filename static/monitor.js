import { h, u, colors, Lines } from './util.js'

export const Monitor = (output) => {

  let signals = null
  let sender = null

  const width=600, height=128, speed=3, lw=1

  const presets = {
    default: new Set([
      'loud',
      'low',
      // 'medium',
      'high',
    ]),
    none: new Set([]),
    all: new Set([]),
    states: new Set([
      'drone1',
      'drone2',
      'flash',
      'sonar',
      'std2',
    ]),
  }
  let preset = presets.default

  const states = ['frozen', 'std', 'std2', 'std3', 'ooo', 'flash', 'test', 'color']
  let overrides = {}
  const disp = h.div().of(
    h.select('logmel_src').of(
      ['input', 'output1l', 'output1r', 'output2l', 'output2r'].map(value => (
          h.option({value}).of(value)
      ))
    ),
    ' overrides: ',
    h.input('overrides', {type: 'text', value: JSON.stringify(overrides)}), h.br(),
    h.canvas('graph', {width, height}),
    h.br(),
    h.div('text_sigs'),
    h.br(),
    h.div('lines').of(
      h.select('preset').of(
        Object.keys(presets).map(preset => (
          h.option({value: preset}).of(preset)))
      ),
      h.br(),
    ),
    h.br(),
    states.map(state => h.button(state).of(state)),
    h.br(),
    h.button('dump').of('dump'),
    h.button('clear').of('clear'),
    h.br(),
    h.pre('output'),
  ).into(output).els

  const lines = Lines(disp.lines)

  disp.overrides.addEventListener('keydown', function(e) {
    if (e.keyCode === 13) {
      if (!sender) {
        console.warn('cannot sed overrides : no sender')
        return
      }
      try {
        overrides = JSON.parse(this.value)
        try {
          console.info('sending overrides', this.value)
          sender({overrides})
        } catch (e) {
          console.warn('could not send', e)
        }
      } catch (e) {
        console.warn('invalid overrides', this.value)
      }
    }
  })

  disp.logmel_src.addEventListener('change', () => {
    if (!sender) {
      return
    }
    sender({logmel_src: disp.logmel_src.value})
    console.info('sent logmel_src', disp.logmel_src.value)
  })

  disp.preset.addEventListener('change', () => {
    preset = presets[disp.preset.value]
    lines.set(preset)
  })

  disp.dump.addEventListener('click', () => {
    disp.output.textContent = JSON.stringify(signals, null, 2)
  })
  disp.clear.addEventListener('click', () => {
    disp.output.textContent = ''
  })

  states.forEach(state => {
    disp[state].addEventListener('click', () => {
      if (!sender) {
        return
      }
      sender({newstate: state})
      console.log('sent newstate', state)
    })
  })

  const ctx = disp.graph.getContext('2d')

  let t=-1, lastys={}
  const nolines = new Set(['logmel', 'mfccs', 't', 'signalin'])
  const text_sigs = new Set(['state', 'position'])
  function listener(data) {
    signals = JSON.parse(data)
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

  function sendto(sender_) {
    sender = sender_
  }

  return {
    listener,
    sendto,
  }
}
