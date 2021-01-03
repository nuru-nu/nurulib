import { h, ui, u, colors } from './util.js'

// Shows signals; monitor_def = {
//     graphs: {
//       group1: [sig1, ...],
//       ...
//     },
//     features: {
//       numbers: [sig2, ...],
//     },
//     hidden: [sig3, ...],
// }
export const Monitor = (output, { monitor_def }) => {

  let signals = null

  const { graphs, features } = monitor_def
  const grid = {ms: 100, dy: 0.1}
  const width=600, height=128, speed=3, lw=1

  const numbers = new Set(features.numbers)
  const hidden = new Set(monitor_def.hidden.concat(monitor_def.transients))
  const known = new Set(), unknown = new Set()
  const addsigs = signals => {for (const signal of signals) known.add(signal)}
  Object.values(graphs).forEach(sigs => addsigs(sigs))
  Object.values(features).forEach(sigs => addsigs(sigs))
  addsigs(hidden)

  const els = ui.v(
    h.canvas('graph', {width, height}),
    h.div('labels', {style: `width: ${width}px`}),
    h.div('state', {style: 'margin-top: 20px'}),
    h.div('features'),
    h.div('unknown', {style: 'margin-top: 20px; color: red'}),
  ).into(output).els

  let graphs_no_hidden = {}
  Object.keys(graphs).forEach(
    group => graphs_no_hidden[group] = graphs[group].filter(
      sig => !hidden.has(sig)))
  const lines = Lines(els.labels, graphs_no_hidden)
  els.graph.addEventListener('click', lines.toggle)
  monitor_def.selected.forEach(lines.set_next_color)
  lines.toggle()

  const ctx = els.graph.getContext('2d')

  let t=-1, lastys={}, gt = 0
  const special = new Set(['logmel', 'mfccs', 't', 'signalin'])
  function listener(data) {
    signals = data
    t++
    if (signals.state.indexOf('frozen') !== -1) {
      els.text_sigs.textContent = signals.state
      return
    }
    if (Date.now() - gt > grid.ms) {
      gt = Date.now()
      for(let y = grid.dy; y < 1; y += grid.dy) {
        ctx.fillStyle = '#0f0'
        ctx.fillRect(width - 2, height * y, 1, 1)
      }
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

    let features = ''
    u.sorted(Object.keys(signals)).forEach(sig => {
      if (sig === 'state') {
        els.state.textContent = signals[sig]
        return
      }
      if (numbers.has(sig)) {
        features += `${sig}=${signals[sig]} `
        return
      }
      const color = lines.get_color(sig)
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
        return
      }
      if (!known.has(sig)) {
        if (!unknown.has(sig)) {
          els.unknown.textContent += `${sig} `
          unknown.add(sig)
        }
      }
    })
    els.features.textContent = features
  }

  return {
    listener,
  }
}

export const Dump = (output, {network}) => {
  const els = h.div().of(
    ui.h(
      ui.toggle('dump'),
      ' - filter: ',
      h.input('include', {type: 'text'}), '\\',
      h.input('exclude', {type: 'text'}),
      ui.toggle('live'),
    ),
    h.pre('output'),
  ).into(output).els

  let include = '', exclude = '', live = false, shown = false

  els.include.addEventListener('keyup', e => {
    include = e.target.value.split(/\s+/g).filter(x => x !== '')
    update()
  })
  els.exclude.addEventListener('keyup', e => {
    exclude = e.target.value.split(/\s+/g).filter(x => x !== '')
    update()
  })

  const matches = s => (
    !include.length || include.some(token => s.search(token) >= 0)
  ) && (
    !exclude.length || exclude.every(token => s.search(token) == -1)
  )

  els.live.change(value => live = value).classList.add('h')
  els.dump.change(value => {
    shown = value
    if (value) {
      els.live.classList.remove('h')
    } else {
      els.live.classList.add('h')
      els.output.textContent = ''
    }
    update()
  })

  function update() {
    els.output.textContent = ''
    if (!shown || !signals) return
    u.sorted(Object.entries(signals)).map(([k, v]) => {
      if (!matches(k)) return
      if (Array.isArray(v) && v.length && 'number' === typeof v[0]) {
        v = `[${v.map(x => x.toFixed(3)).join(',')}]`
      } else if ('object' === typeof v) {
        v = JSON.stringify(v)
      } else if ('number' === typeof v) {
        v = v.toFixed(4)
      }
      els.output.textContent += `${k} = ${v}\n`
    })
  }

  let signals = null
  network.listenJson('signals', function(data) {
    signals = data
    if (shown && live) update()
  })
}

// Manages checkboxes and graph line styles.
function Lines(output, graphs) {

  const els = h.div().of(
    h.div('summary .summary', { display: 'none' }),
    h.table('table .lines').of(
      Object.keys(graphs).map(group =>
        h.tr().of(
          h.td().of(group),
          h.td().of(
            ui.h(h.div(`${group} .flex`)).of(
              graphs[group].map(sig => [
                h.input(`checkbox_${sig} #line_${sig}`, { type: 'checkbox' }),
                h.label(`label_${sig} .notyet`, { for: `line_${sig}` }).of(sig),
              ]
              ),
            ),
          ),
        ),
      ),
    ),
  ).into(output).els

  const palette = colors.strong_palette
  let available = Array.from(palette)
  let toggled = false

  let lines = {}

  function set_color(sig, color) {
    lines[sig] = {color, t: Date.now()}
    els[`label_${sig}`].style.backgroundColor = color
    els[`label_${sig}`].style.color = 'black'
    els[`checkbox_${sig}`].checked = true
  }

  function set_next_color(sig) {
    if (lines.sig && lines[sig].t) {
      return
    }
    if (!available.length) {
      // switch with oldest color
      let oldest=null, min_t=new Date().getTime()
      u.sorted(Object.keys(lines)).forEach(sig => {
        if (lines[sig].t < min_t) {
          min_t = lines[sig].t
          oldest = sig
        }
      })
      remove_color(oldest)
    }
    set_color(sig, available.shift())
  }

  function remove_color(sig) {
    if (!sig || !lines[sig].t) {
      return
    }
    available.unshift(lines[sig].color)
    delete lines[sig]
    els[`label_${sig}`].style = {}
    els[`checkbox_${sig}`].checked = false
  }

  Object.keys(graphs).forEach(group =>
    graphs[group].forEach(sig =>
      els[`checkbox_${sig}`].addEventListener('change', function () {
        if (this.checked) {
          set_next_color(sig)
        } else {
          remove_color(sig)
        }
      })
    )
  )

  function get_color(sig) {
    const label = els[`label_${sig}`]
    if (label) label.classList.remove('notyet')
    return lines[sig] && lines[sig].color
  }

  function toggle() {
    toggled = !toggled
    if (toggled) {
      els.table.style.display = 'none'
      u.empty(els.summary)
      Object.keys(lines).forEach(sig => {
        h.span().of(sig).into(els.summary).el.style.color = lines[sig].color
      })
      els.summary.style.display = 'block'
    } else {
      els.table.style.display = 'block'
      els.summary.style.display = 'none'
    }
  }

  return {
    set_next_color,
    get_color,
    toggle,
  }
}
