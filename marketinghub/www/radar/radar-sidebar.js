/* Sidebar compartido del modulo Radar.
 *
 * Cada pagina de /radar/* es un documento independiente (unas standalone y
 * otras extendiendo templates/web.html), asi que en vez de duplicar el markup
 * en 10 plantillas se inyecta desde aqui: basta con incluir radar-sidebar.css
 * y este script. Marca el item activo por la URL y pide los contadores al
 * backend. El estado colapsado se recuerda en localStorage.
 */
(function () {
  var STORAGE_KEY = 'radx-collapsed';
  var ICON = {
    marca: '<path d="M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17z M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z M12 11.4a.6.6 0 1 0 0 1.2.6.6 0 0 0 0-1.2z"/>',
    publicaciones: '<path d="M12 3.5s4.5 3.6 4.5 8a4.5 4.5 0 0 1-9 0c0-1.6.8-2.9 1.6-3.8 0 1.6.9 2.4 1.6 2.4 1 0 1.3-1 1.3-2.3 0-1.6-.5-3.1-1-4.3z M8 15.5a4 4 0 0 0 8 0"/>',
    guiones: '<path d="M4 20l1-4 10.5-10.5 3 3-10.5 10.5z M14.5 6.5l3 3"/>',
    calendario: '<path d="M4.5 6.5h15v13.5h-15z M8.5 3.5v4 M15.5 3.5v4 M4.5 11h15"/>',
    agenda: '<path d="M8 6.5h12 M8 12h12 M8 17.5h12 M4 6.5h.01 M4 12h.01 M4 17.5h.01"/>',
    ads: '<path d="M4 6.5h16v11H4z M4 10h16 M8 6.5v11"/>',
    competidores: '<path d="M6.5 3.5v17 M6.5 4.5h11l-2.2 3.8 2.2 3.7h-11"/>',
    cuentas: '<path d="M12 7.8a4.2 4.2 0 1 0 0 8.4 4.2 4.2 0 0 0 0-8.4z M16.2 7.8v5.1a3 3 0 0 0 5.3 1.9 M20 15.9A9 9 0 1 1 18.4 5.6"/>',
    categorias: '<path d="M4 4.5h7l9 9-6.5 6.5-9-9z M7.6 8.1h.01"/>',
    ajustes: '<path d="M12 8.6a3.4 3.4 0 1 0 0 6.8 3.4 3.4 0 0 0 0-6.8z M19.4 14.2a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1v.2a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-2.8-1.1l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0-1.1-2.7H3.4a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.1-2.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 2.7-1.1V3.4a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0 1.1 2.7h.2a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.4 1.1z"/>',
    tema: '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/>',
    ocultar: '<path d="M14 6l-6 6 6 6"/>',
    mostrar: '<path d="M10 6l6 6-6 6"/>'
  };

  var GRUPOS = [
    {
      titulo: 'Contenido',
      items: [
        { href: '/radar/publicaciones', icono: 'publicaciones', label: 'Publicaciones', count: 'publicaciones', destacado: true },
        { href: '/radar/guiones', icono: 'guiones', label: 'Guiones', count: 'guiones' },
        { href: '/radar/comparativa', icono: 'calendario', label: 'Calendario pubs' },
        { href: '/radar/guiones?vista=calendario', icono: 'agenda', label: 'Agenda guiones', count: 'guiones_semana' },
        { href: '/radar/ads', icono: 'ads', label: 'Ads Library', count: 'ads' }
      ]
    },
    {
      titulo: 'Configuración',
      items: [
        { href: '/radar/competidores', icono: 'competidores', label: 'Competidores', count: 'competidores' },
        { href: '/radar/cuentas', icono: 'cuentas', label: 'Cuentas', count: 'cuentas' },
        { href: '/radar/categorias', icono: 'categorias', label: 'Categorías', count: 'categorias' },
        { href: '/radar/settings', icono: 'ajustes', label: 'Ajustes' }
      ]
    }
  ];

  function svg(nombre, tam) {
    return '<svg viewBox="0 0 24 24" width="' + tam + '" height="' + tam + '" fill="none" stroke="currentColor" ' +
      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + ICON[nombre] + '</svg>';
  }

  // El item activo se decide por ruta + query: /radar/guiones y
  // /radar/guiones?vista=calendario son entradas distintas del menu.
  function esActivo(href) {
    var url = new URL(href, window.location.origin);
    if (url.pathname !== window.location.pathname) return false;
    var vistaMenu = url.searchParams.get('vista');
    var vistaActual = new URLSearchParams(window.location.search).get('vista');
    return (vistaMenu || '') === (vistaActual || '');
  }

  function construir() {
    var aside = document.createElement('aside');
    aside.className = 'radx-side';
    aside.id = 'radx-side';

    var html = '' +
      '<div class="radx-top">' +
        '<a class="radx-brand" href="/radar" title="Radar">' + svg('marca', 17) + '<span>Radar</span></a>' +
        '<button class="radx-toggle" id="radx-toggle" type="button" title="Ocultar menú" aria-label="Ocultar menú">' +
          svg('ocultar', 15) +
        '</button>' +
      '</div>' +
      '<div class="radx-body">';

    GRUPOS.forEach(function (grupo) {
      html += '<div class="radx-group"><div class="radx-group__title">' + grupo.titulo + '</div>';
      grupo.items.forEach(function (item) {
        html += '<a class="radx-nav' + (esActivo(item.href) ? ' is-active' : '') + '" href="' + item.href + '" title="' + item.label + '">' +
          '<span class="radx-nav__label">' + svg(item.icono, 15) + '<span>' + item.label + '</span></span>' +
          '<span class="radx-nav__count"' + (item.count ? ' data-count="' + item.count + '"' : '') + '></span>' +
        '</a>';
      });
      html += '</div>';
    });

    html += '</div>';

    // El boton de tema solo aparece si la pagina trae su propio toggle: cada
    // una persiste el tema con su propia clave, asi que delegamos en el suyo.
    var toggleTema = document.querySelector('#theme-toggle, #themeBtn');
    if (toggleTema && !toggleTema.closest('.radx-side')) {
      html += '<div class="radx-foot">' +
        '<button class="radx-themebtn" id="radx-theme" type="button" title="Cambiar tema">' +
          svg('tema', 15) + '<span>Cambiar tema</span>' +
        '</button>' +
      '</div>';
    }

    aside.innerHTML = html;
    return aside;
  }

  function aplicarEstado(colapsado) {
    document.body.classList.toggle('radx-collapsed', colapsado);
    var btn = document.getElementById('radx-toggle');
    if (!btn) return;
    btn.innerHTML = svg(colapsado ? 'mostrar' : 'ocultar', 15);
    btn.title = colapsado ? 'Mostrar menú' : 'Ocultar menú';
    btn.setAttribute('aria-label', btn.title);
  }

  function cargarContadores(aside) {
    var celdas = aside.querySelectorAll('[data-count]');
    if (!celdas.length) return;
    fetch('/api/method/marketinghub.www.radar.index.obtener_contadores', {
      credentials: 'same-origin',
      headers: { 'Accept': 'application/json' }
    })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        var counts = data && data.message;
        if (!counts) return;
        celdas.forEach(function (celda) {
          var valor = counts[celda.dataset.count];
          celda.textContent = valor ? valor : '';
        });
      })
      .catch(function () { /* sin contadores; el menu sigue usable */ });
  }

  function init() {
    if (document.getElementById('radx-side')) return;
    // dentro de /panel la pagina va en un iframe y el sidebar lo pone el panel
    if (window.self !== window.top) return;
    // Las paginas de error/acceso denegado no llevan menu.
    if (document.body.dataset.radxSide === 'off') return;

    var aside = construir();
    document.body.insertBefore(aside, document.body.firstChild);
    document.body.classList.add('radx-has-side');

    var guardado = null;
    try { guardado = localStorage.getItem(STORAGE_KEY); } catch (e) {}
    var colapsado = guardado === null ? window.innerWidth <= 860 : guardado === '1';
    aplicarEstado(colapsado);

    document.getElementById('radx-toggle').addEventListener('click', function () {
      var nuevo = !document.body.classList.contains('radx-collapsed');
      aplicarEstado(nuevo);
      try { localStorage.setItem(STORAGE_KEY, nuevo ? '1' : '0'); } catch (e) {}
    });

    var btnTema = document.getElementById('radx-theme');
    if (btnTema) {
      btnTema.addEventListener('click', function () {
        var nativo = document.querySelector('#theme-toggle, #themeBtn');
        if (nativo && !nativo.closest('.radx-side')) nativo.click();
      });
    }

    cargarContadores(aside);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
