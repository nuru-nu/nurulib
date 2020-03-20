import { h } from './util.js'

export const Network = (output, options) => {
  const record_timestamps = (options || {}).record_timestamps || false

  const host = window.location.hostname
  const signals_port = 6108
  const animation_port = 6109

  const timestamps = { animation: [], signals: [] }

  const socks = {
    animation: new WebSocket(`ws://${window.location.host}/+animation`),
    signals: new WebSocket(`ws://${window.location.host}/+signals`),
  }

  const disp = h.div().of(
    'animation ', h.span('animation').of('connecting'),
    ', signals ', h.span('signals').of('connecting')
  ).into(output).els;

  let animation_listeners = [], signals_listeners = []

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

  let listeners = {}
  Object.keys(socks).forEach(key => listeners[key] = [])

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
  socks.signals.addEventListener('message', function (e) {
    if (record_timestamps) {
      timestamps.signals.push(new Date().getTime())
    }
    if (e.data instanceof Blob) {
      new Response(e.data).text().then(function(data) {
        listeners.signals.forEach(listener => listener(data))
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

  function sender(d) {
    console.log('>>>', d)
    socks.signals.send(JSON.stringify(d))
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
    sender,
    download_timestamps,
  }
}

