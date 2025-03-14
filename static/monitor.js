import { h, ui, u, colors, observe } from './util.js'

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

  const hidden = new Set(monitor_def.hidden.concat(monitor_def.transients))
  const known = new Set(), unknown = new Set()
  const addsigs = signals => {for (const signal of signals) known.add(signal)}
  Object.values(graphs).forEach(sigs => addsigs(sigs))
  const feature_map = {}
  const groups = []
  Object.keys(features).forEach(group => {
    groups.push(h.div().of(
      h.span().of(`${group}: `),
      features[group].map(sig => {
        known.add(sig)
        const name = `feature_${sig}`
        feature_map[sig] = name
        return [` ${sig}=`, h.span(name).of('?')]
      })
    ))
  })
  addsigs(hidden)

  const els = ui.v(
    ui.h(
      ui.toggle('logmel'),
      ui.choice('selected', {values: Object.keys(monitor_def.selected)}),
    ),
    h.canvas('graph', {width, height}),
    h.div('labels', { style: `width: ${width}px` }),
    h.div().of(groups),
    h.div('unknown', { style: 'margin-top: 20px; color: red' }),
  ).into(output).els

  let graphs_no_hidden = {}
  Object.keys(graphs).forEach(
    group => graphs_no_hidden[group] = graphs[group].filter(
      sig => !hidden.has(sig)))
  const lines = Lines(els.labels, graphs_no_hidden)
  els.graph.addEventListener('click', lines.toggle)
  els.selected.change(selected => {
    lines.clear()
    monitor_def.selected[selected].forEach(lines.set_next_color)
  })
  Object.values(monitor_def.selected)[0].forEach(lines.set_next_color)
  lines.toggle()

  const ctx = els.graph.getContext('2d')

  let running = true
  // observe(els.graph).start(() => running=true).stop(() => running=false)

  let t=-1, lastys={}, gt = 0
  function listener(data) {
    if (!running) return
    signals = data
    t++
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

    if (els.logmel.get() && signals.hasOwnProperty('logmel')) {
      signals.logmel.forEach((value, i) => {
        value = (value + 5) / 10
        value = Math.min(1, Math.max(0, value))
        ctx.fillStyle = colors.greens[Math.floor(255 * value)]
        ctx.fillRect(width - speed - 1, height - i * 2, speed, 2)
      })
    }

    const ys = new Set()
    u.sorted(Object.keys(signals)).forEach(sig => {
      if (feature_map.hasOwnProperty(sig)) {
        els[feature_map[sig]].textContent = signals[sig]
        return
      }

      const color = lines.get_color(sig)
      if (color) {
        let y = Math.floor((height - lw) * (1 - signals[sig]))
        if (y < height / 2) {
          while (ys.has(y)) y += lw
        } else {
          while (ys.has(y)) y -= lw
        }
        ys.add(y)
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
  }

  return {
    listener,
  }
}

export const Dump = (output, {network}) => {
  const wraplength = 150
  const els = h.div('cont').of(
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
    update(e.keyCode)
  })
  els.exclude.addEventListener('keyup', e => {
    exclude = e.target.value.split(/\s+/g).filter(x => x !== '')
    update(e.keyCode)
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

  function update(keyCode) {
    if (keyCode === 13) {
      if (!shown) els.dump.click()
      els.live.click()
    }
    if (keyCode === 27) {
      if (shown) els.dump.click()
    }
    els.output.textContent = ''
    if (!shown || !signals) return

    function dumpobj(x) {
      if (x === null) return 'null'
      function dumpv(v) {
        if ('object' === typeof v) {
          return dumpobj(v)
        } else if ('number' === typeof v) {
          if (v != Math.floor(v)) v = v.toFixed(2)
          return v
        } else {
          return JSON.stringify(v)
        }
      }
      if (Array.isArray(x)) {
        return '[' + x.map(dumpv).join(',') + ']'
      }
      return '{' + Object.entries(x).map(kv => [kv[0], dumpv(kv[1])].join(':')).join(',') + '}'
    }

    u.sorted(Object.entries(signals)).map(([k, v]) => {
      if (!matches(k)) return
      if (Array.isArray(v) && v.length && 'number' === typeof v[0]) {
        v = `[${v.map(x => x.toFixed(3)).join(',')}]`
      } else if ('object' === typeof v) {
        v = dumpobj(v)
      } else if ('number' === typeof v) {
        v = v.toFixed(4)
      }
      let prefix = `${k} = `
      const l = Math.max(10, wraplength - prefix.length)
      let wrapped = ''
      while (v.length) {
        wrapped += prefix + v.slice(0, l) + '\n'
        v = v.slice(l)
        prefix = Array(prefix.length).fill(' ').join('')
      }
      els.output.textContent += wrapped
    })
  }

  let running = true
  observe(els.cont).start(() => running=true).stop(() => running=false)

  let signals = null
  network.listenJson('signals', function(data) {
    signals = data
    if (shown && live && running) update()
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

  const palette = colors.monitor_colors
  let available = Array.from(palette)
  let toggled = false

  let lines = {}

  function set_color(sig, color) {
    lines[sig] = {color, t: Date.now()}
    if (els.hasOwnProperty(`label_${sig}`)) {
      els[`label_${sig}`].style.backgroundColor = color
      els[`label_${sig}`].style.color = 'black'
      els[`checkbox_${sig}`].checked = true
    }
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
    update_summary()
  }

  function remove_color(sig) {
    if (!sig || !lines[sig].t) {
      return
    }
    available.unshift(lines[sig].color)
    delete lines[sig]
    if (els.hasOwnProperty(`label_${sig}`)) {
      els[`label_${sig}`].style = {}
      els[`checkbox_${sig}`].checked = false
    }
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

  function update_summary() {
    u.empty(els.summary)
    Object.keys(lines).forEach(sig => {
      h.span().of(sig).into(els.summary).el.style.color = lines[sig].color
    })
  }

  function toggle() {
    toggled = !toggled
    if (toggled) {
      els.table.style.display = 'none'
      update_summary()
      els.summary.style.display = 'block'
    } else {
      els.table.style.display = 'block'
      els.summary.style.display = 'none'
    }
  }

  function clear() {
    u.empty(els.summary)
    Object.keys(graphs).forEach(group =>
      graphs[group].forEach(sig => {
        const cb = els[`checkbox_${sig}`]
        if (cb.checked) {
          cb.checked = false
          remove_color(sig)
        }
      })
    )
    available = Array.from(palette)
  }

  return {
    set_next_color,
    get_color,
    toggle,
    clear,
  }
}
