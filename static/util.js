
// Not so painful HTML generation:
// let els = h.div('.outer').of(
//   h.div('first .row'),
//   buttons.map(text => h.button(text).of(text))
// ).into('#output').els
// els[buttons[0]].addEventListener('click', ...)
// ... see also `ui` below ...
export const h = (function() {
  function isNode(x) {
    return x instanceof HTMLElement
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
        if (el.name) this.els[el.name] = el
      } else if (typeof el === 'string' || typeof el === 'number') {
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
    'a', 'div', 'span', 'button', 'pre', 'canvas', 'br',
    'input', 'label', 'select', 'option', 'table', 'tr', 'td',
  ]
  tags.forEach(tag => {
    ns[tag] = function() {
      return H.apply(null, [tag, ...arguments])
    }
  })
  return ns
})();

// Synposis:
// ui.h(ui.v('top', 'bottom'), 'right')
// ui.choice({values: ['A', 'B']})
// ui.dropdown({values: ['A', 'B']})
// ui.toggle(name)
// ui.range(name)
// *[.change(value =>)][.init()]
export const ui = (() => {

  const updater = (el, getter) => {
    const listeners = new Set()
    el.change = listener => {
      listeners.add(listener)
      return el
    }
    el.init = () => {
      listeners.forEach(listener => listener(getter()))
      return el
    }
    return () => {
      Array.from(listeners).map(listener => listener(getter()))
    }
  }

  const choice = (name, {values, initial}) => {
    let value = initial || values[0]
    const disp = h.div('cont', {class: 'flex'}).of(
      values.map(value => h.button(value).of(value))
    ).els
    const update = updater(disp.cont, () => value)
    function set(value_) {
       value = value_
      values.map(value => disp[value].classList.remove('on'))
      disp[value].classList.add('on')
      disp.cont.value = value
    }
    values.map(value => disp[value].addEventListener('click', () => {
      set(value)
      update()
    }))
    set(value)
    disp.cont.name = name
    return disp.cont
  }

  const dropdown = (name, {values, initial}) => {
    initial = initial || values[0]
    const select = h.select().of(
      values.map(value => h.option({value}).of(value))
    ).el
    const update = updater(select, () => select.value)
    select.addEventListener('change', update)
    select.value = initial
    select.name = name
    return select
  }

  const range = (name, opts) => {
    opts = opts || {}
    const value = opts.value || 0
    const range = h.input(name, {type: 'range', min: 0, max: 1, step: .01, value}).el
    const update = updater(range, () => range.value)
    range.addEventListener('input', update)
    return range
  }

  const toggle = (name, initial) => {
    let value = initial || false
    const button = h.button(initial && '.on').of(name).el
    button.name = name
    const update = updater(button, () => value)
    button.addEventListener('click', () => {
      value = !value
      button.classList[value ? 'add' : 'remove']('on')
      update()
    })
    return button
  }

  function v() { return h.div().of(Array.from(arguments)) }
  function h_() { return h.div({class: 'flex'}).of(Array.from(arguments)) }
  function hw() {
    const ret = h_.apply(null, arguments)
    ret.el.style.flexWrap = 'wrap'
    return ret
  }

  return {
    choice,
    dropdown,
    range,
    h: h_,
    hw,
    toggle,
    v,
  }
})();

// Some handy utilities.
export const u = function() {
  function sorted(a) {
    let b = Array.from(a)
    b.sort()
    return b
  }
  function empty(el) {
    while (el.firstChild) el.removeChild(el.firstChild)
  }
  return {
    sorted,
    empty,
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
  const user_colors = [
    '#0000ff', '#00ff00', '#ff0000', '#00ffff', '#ffff00', '#ff00ff',
    '#c0c0c0', '#808080', '#000080', '#008080', '#008000', '#800080',
    '#808000', '#800000'
  ]

  return {
    hex2,
    greens,
    rgb,
    rgbf,
    palette1,
    palette2,
    strong_palette,
    user_colors,
  }
}()

// for replacing window.console
export const Console = function(output) {
  const console = window.console

  const disp = h.div('.scrollable').of(h.div('console')).into(output).els

  function clear() {
    u.empty(disp.console)
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
