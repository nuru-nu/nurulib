
// Not so painful HTML generation.
// let stuff = h.div('.outer').of(h.div('first .row'), div('second .row'))
// stuff.into(document.getElementById('output'))
// stuff.els.first.addEventListener('click', ...)
export const h = (function() {
  function isNode(x) {
    return x.hasOwnProperty('baseURI')
  }
  function isH(x) {
    return x.hasOwnProperty('_els')
  }
  function recarr(arr, f) {
    arr.forEach(el => Array.isArray(el) ? recarr(el, f) : f(el))
  }
  function of() {
    recarr(Array.from(arguments), el => {
      if (isNode(el)) {
      } else if (typeof el === 'string') {
        el = document.createTextNode(el)
      } else if (isH(el)) {
        this._els = [...this._els, ...el._els]
        this.els = {...this.els, ...el.els}
        el = el.el
      } else {
        console.log('Unknown type', el)
        throw `Unknown type: ${el}`
      }
      this.el.appendChild(el)
    })
    return this
  }
  function into(target) {
    if (target.el) {
      el = target.el
    } else if (typeof target === 'string') {
      target = document.querySelector(target)
    }
    target.appendChild(this.el)
    return this
  }
  function click(cb) {
    this.el.addEventListener('click', cb)
    return this
  }
  function toggle(cb, initial) {
    this.el.classList.add('toggle')
    if (initial) {
      this.el.classList.add('on')
    }
    this.el.addEventListener('click', function() {
      this.classList.toggle('on')
      const value = this.classList.contains('on')
      cb.apply(this, value)
    })
    return this
  }
  function _H() {
    return {
      // All named elements.
      els: {},
      // All unnamed elements.
      _els: [],
      // Last element.
      el: null,
      // Inserts list of elements into `el`.
      of,
      // Inserts `el` into provided target.
      into,
      // Simple behavior.
      click,
      toggle,
    }
  }
  function H(tag, specs, attrs) {
    let ret = _H(), name, el = document.createElement(tag);
    if (typeof specs === 'object') {
      attrs = specs
      specs = null
    }
    (specs || '').split(' ').forEach((arg, i) => {
      if (arg[0] === '#') {
        el.setAttribute('id', arg.substr(1))
      } else if (arg[0] === '.') {
        el.classList.add(arg.substr(1))
      } else {
        if (i === 0) {
          name = arg
          return
        }
        throw `Unknown spec arg: ${arg}`
      }
    })
    if (attrs) {
      Object.keys(attrs).forEach(name => {
        el.setAttribute(name, attrs[name])
      })
    }
    if (name) {
      ret.els[name] = el
    } else {
      ret._els.push(el)
    }
    ret.el = el
    return ret
  }
  let ns = {}
  let tags = [
    'div', 'span', 'button', 'pre', 'canvas', 'br',
    'input', 'label', 'select', 'option'
  ]
  tags.forEach(tag => {
    ns[tag] = function() {
      return H.apply(null, [tag, ...arguments])
    }
  })
  return ns
})();

// Some handy utilities.
export const u = function() {
  function sorted(a) {
    let b = Array.from(a)
    b.sort()
    return b
  }
  return {
    sorted,
  }
}()

// Output stats; returns callable for listening to streaming data.
export function Stats(output) {
  let el = h.div('.stats').into(output).el
  let lt=0, hz=1, i=0, li=0, sum=0
  function digest(bytes) {
    const t = new Date().getTime() / 1e3
    i++
    if (bytes.hasOwnProperty('bytesLength')) {
      sum += bytes.byteLength
    } else {
      sum += bytes.length
    }
    if ((t - lt) * hz > 1) {
      const fps = (i - li) / (t - lt)
      const now = new Date().toISOString().substr(11, 8)
      const mb = sum / 1e6
      el.textContent = `${now} - i=${i} sum=${mb.toFixed(1)}M fps=${fps.toFixed(1)}`
      lt = t
      li = i
    }
  }
  return digest
}

// Some color related helpers.
export const colors = function() {

  const hex2 = Array.from(Array(256).keys()).map(function (v) {
    return (v < 16 ? '0' : '') + v.toString(16)
  })
  const greens = Array.from(Array(256).keys()).map(function (v) {
    return '#00' + hex2[v] + '00'
  })
  function rgb(r, g, b) {
    return '#' + hex2(r) + hex2(g) + hex2(b)
  }
  function rgbf(r, g, b) {
    return rgb(
      Math.floor(255 * r),
      Math.floor(255 * g),
      Math.floor(255 * b)
    )
  }

  // https://medialab.github.io/iwanthue/
  // C45..100 L35..80
  const palette1 = [
    '#d545b6', '#50b654', '#b543dc', '#91a636', '#6d55d9',
    '#cc8f35', '#6474d2', '#d35237', '#b568bf', '#d34676'
  ]
  // fluo https://www.color-hex.com/color-palette/19121
  const palette2 = [
    '#a3f307', '#05f9e2', '#e2f705', 'f50b86', '#ff6f00',
  ]
  const strong_palette = [
    '#0000ff', '#ff0000', '#ffff00', '#00ffff', '#ff00ff', '#00ff00',
    '#ffffff',
  ]

  return {
    hex2,
    greens,
    rgb,
    rgbf,
    palette1,
    palette2,
    strong_palette,
  }
}()

// Manages checkboxes and graph line styles.
export const Lines = function(output) {

  const palette = colors.strong_palette
  let available = Array.from(palette)
  let cols_i = 0

  let lines = {}

  function set_color(sig, color) {
    lines[sig].color = color
    lines[sig].t = new Date().getTime()
    lines[sig].label.style.backgroundColor = color
    lines[sig].label.style.color = 'black'
    lines[sig].checkbox.checked = true
  }

  function set_next_color(sig) {
    if (lines[sig].t) {
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
    if (!lines[sig].t) {
      return
    }
    delete lines[sig].t
    available.unshift(lines[sig].color)
    delete lines[sig].color
    lines[sig].label.style = {}
    lines[sig].checkbox.checked = false
  }

  function get(sig, t, preset) {
    if (!lines.hasOwnProperty(sig)) {
      const n = Object.keys(lines).length
      const els = h.span().of(
        h.input(`checkbox #line_${sig}`, {type: 'checkbox'}),
        h.label('label', {for: `line_${sig}`}).of(sig),
        ' ',
      ).into(output).els
      lines[sig] = { ...els, color: null }
      if (preset && preset.has(sig)) {
        set_next_color(sig)
      }
      lines[sig].checkbox.addEventListener('change', function() {
        if (this.checked) {
          set_next_color(sig)
        } else {
          remove_color(sig)
        }
      })
    }
    return lines[sig].color
  }

  function set(preset) {
    const sigs = u.sorted(Object.keys(lines))
    sigs.forEach(sig => {
      remove_color(sig)
    })
    available = Array.from(palette)
    sigs.forEach(sig => {
      if (preset.has(sig)) {
        set_next_color(sig)
      }
    })
  }

  return {
    get,
    set,
  }
}

// for replacing window.console
export const Console = function(output) {
  const console = window.console

  const disp = h.div('.hide-scroll').of(h.div('console')).into(output).els

  function clear() {
    while (disp.console.firstChild) {
      disp.console.remove(disp.console.firstChild)
    }
    console.clear()
  }

  function wrap(which) {
    function wrapper() {
      console[which].apply(null, arguments)
      const el = document.createElement('div')
      let text = new Date().toTimeString().substr(0, 9)
      Array.from(arguments).forEach(arg => {
        if ('string' !== typeof arg) {
          arg = JSON.stringify(arg)
        }
        text += `${arg} `
      })
      el.textContent = text
      el.classList.add(`console-${which}`)
      disp.console.insertBefore(el, disp.console.firstChild)
    }
    return wrapper
  }

  window.onerror = (message, source, lineno, colno, error) => {
   wrap('error')('FATAL ERROR : ', message, ' : ', error.stack);
  }

  let funcs = {
    clear,
  };
  ['log', 'debug', 'info', 'warn', 'error'].forEach(which => {
    funcs[which] = wrap(which)
  })

  return funcs
}
