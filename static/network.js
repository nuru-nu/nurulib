import { h } from './util.js'

export const Network = (output, options) => {
  options = options || {}
  const record_timestamps = options.record_timestamps || false
  const secondary = options.secondary || false
  const timestamps = { animation: [], signals: [] }

  const socks = {
    signals: new WebSocket(`ws://${window.location.host}/+signals`),
  }
  if (!secondary) {
    socks.animation = new WebSocket(`ws://${window.location.host}/+animation`)
  }

  const disp = h.div().of(
    'animation ', h.span('animation').of('connecting'),
    ', signals ', h.span('signals').of('connecting')
  ).into(output).els;

  Object.keys(socks).forEach(key => {
    let mayberror = ''
    socks[key].addEventListener('open', function (e) {
      disp[key].textContent = 'connnected'
    })
    socks[key].addEventListener('close', function (e) {
      disp[key].textContent = mayberror + 'closed'
    })
    socks[key].addEventListener('error', function (e) {
      mayberror = 'ERROR - '
      console.log(key, 'ERROR', e)
    })
  })

  let listeners = {}, jsonListeners = new Set()
  Object.keys(socks).forEach(key => listeners[key] = [])

  if (!secondary) {
    socks.animation.addEventListener('message', function (e) {
      if (record_timestamps) {
        timestamps.animation.push(new Date().getTime())
      }
      if (e.data instanceof Blob) {
        new Response(e.data).arrayBuffer().then(function(data) {
          let view = new Uint8Array(data)
          listeners.animation.forEach(listener => listener(view))
        })
        return
      }
      console.log('unexpected data type', e.data)
      throw 'unexpected data type'
    })
  }

  let parse_t0 = Date.now()
  let last_json = {}
  socks.signals.addEventListener('message', function (e) {
    if (record_timestamps) {
      timestamps.signals.push(new Date().getTime())
    }
    if (e.data instanceof Blob) {
      new Response(e.data).text().then(data => {
        let json
        try {
          json = JSON.parse(data)
          Object.assign(last_json, json)
          if (!last_json._full) return
        } catch (e) {
          if (Date.now() - parse_t0 > 1000) {
            console.error('Could not parse JSON', data)
            parse_t0 = Date.now()
          }
          return
        }
        listeners.signals.forEach(listener => {
          listener(jsonListeners.has(listener) ? last_json : data)
        })
      })
      return
    }
    console.log('unexpected data type', e.data)
    throw 'unexpected data type'
  })

  function listen(key, listener) {
    listeners[key].push(listener)
    return this
  }
  function listenJson(key, listener) {
    jsonListeners.add(listener)
    return this.listen(key, listener)
  }

  function sender(d, silent) {
    if (!silent) console.log('>>>', d)
    if (socks.signals.readyState === socks.signals.OPEN) {
      socks.signals.send(JSON.stringify(d))
    }
  }

  function download(name, ts) {
    const blob = new Blob([ts.join('\n')], {type: 'text/csv'})
    let el = document.createElement('a')
    el.href = URL.createObjectURL(blob)
    el.download = name
    document.body.appendChild(el)
    el.click()
    document.body.removeChild(el)
  }

  function download_timestamps() {
    if (!record_timestamps) {
      window.alert('not recording timestamps')
      return
    }
    Object.keys(timestamps).forEach(key => {
      download(`timestamps_${key}.csv`, timestamps[key])
    })
  }

  return {
    listen,
    listenJson,
    sender,
    download_timestamps,
    fetch: path => fetch(path),
  }
}

