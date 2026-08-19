/* Navbar horizontal del modulo Radar (N1 — Opcion B).
 *
 * Antes era un <aside> lateral; ahora es un <nav> sticky arriba con las 6
 * secciones como tabs (patron Shalom Pro). Cada pagina /radar/* sigue siendo
 * un documento independiente: al hacer click en una tab, navega a esa URL.
 *
 * El script se llama radar-sidebar.js por compatibilidad — todas las plantillas
 * lo referencian por ese nombre. Solo cambia lo que hace por dentro.
 */
(function () {
  var ICON = {
    marca: '<path d="M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17z M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z M12 11.4a.6.6 0 1 0 0 1.2.6.6 0 0 0 0-1.2z"/>',
    metricas: '<path d="M3 3v18h18 M7 15l4-4 3 3 5-6"/>',
    publicaciones: '<path d="M12 3.5s4.5 3.6 4.5 8a4.5 4.5 0 0 1-9 0c0-1.6.8-2.9 1.6-3.8 0 1.6.9 2.4 1.6 2.4 1 0 1.3-1 1.3-2.3 0-1.6-.5-3.1-1-4.3z M8 15.5a4 4 0 0 0 8 0"/>',
    calendario: '<path d="M4.5 6.5h15v13.5h-15z M8.5 3.5v4 M15.5 3.5v4 M4.5 11h15"/>',
    ads: '<path d="M4 6.5h16v11H4z M4 10h16 M8 6.5v11"/>',
    competidores: '<path d="M6.5 3.5v17 M6.5 4.5h11l-2.2 3.8 2.2 3.7h-11"/>',
    ajustes: '<path d="M12 8.6a3.4 3.4 0 1 0 0 6.8 3.4 3.4 0 0 0 0-6.8z M19.4 14.2a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1v.2a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-2.8-1.1l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0-1.1-2.7H3.4a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.1-2.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 2.7-1.1V3.4a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0 1.1 2.7h.2a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.4 1.1z"/>',
    tema: '<path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z"/>'
  };

  /* Lista plana de tabs — orden = orden visual en el navbar.
     Los items internos «Cuentas» y «Categorias» ya viven dentro de Competidores
     (acordeon + modal ⚙️), asi que no son tabs. */
  var TABS = [
    { href: '/radar/metricas',       icono: 'metricas',       label: 'Métricas' },
    { href: '/radar/publicaciones',  icono: 'publicaciones',  label: 'Publicaciones', count: 'publicaciones' },
    { href: '/radar/comparativa',    icono: 'calendario',     label: 'Calendario' },
    { href: '/radar/ads',            icono: 'ads',            label: 'Ads Library', count: 'ads' },
    { href: '/radar/competidores',   icono: 'competidores',   label: 'Competidores', count: 'competidores' },
    { href: '/radar/settings',       icono: 'ajustes',        label: 'Ajustes' }
  ];

  function svg(nombre, tam) {
    return '<svg viewBox="0 0 24 24" width="' + tam + '" height="' + tam + '" fill="none" stroke="currentColor" ' +
      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + ICON[nombre] + '</svg>';
  }

  /* Activo si el pathname coincide. Diferencias como ?vista=calendario
     tambien matchean el mismo href (una tab, misma URL). */
  function esActivo(href) {
    var url = new URL(href, window.location.origin);
    return url.pathname === window.location.pathname;
  }

  function construir() {
    var nav = document.createElement('nav');
    nav.className = 'radx-topbar';
    nav.id = 'radx-side';   // ID legacy conservado por si algo lo referencia

    var tabs = TABS.map(function (t) {
      return '<a class="radx-tab' + (esActivo(t.href) ? ' is-active' : '') + '" href="' + t.href + '" title="' + t.label + '">' +
        svg(t.icono, 14) +
        '<span class="radx-tab__label">' + t.label + '</span>' +
        '<span class="radx-tab__count"' + (t.count ? ' data-count="' + t.count + '"' : '') + '></span>' +
      '</a>';
    }).join('');

    /* Boton de tema — solo si la pagina expone su propio toggle (cada una
       persiste el tema con clave distinta, delegamos). */
    var pagTema = document.querySelector('#theme-toggle, #themeBtn');
    var tema = (pagTema && !pagTema.closest('.radx-topbar'))
      ? '<button class="radx-themebtn" id="radx-theme" type="button" title="Cambiar tema">' + svg('tema', 14) + '</button>'
      : '';

    nav.innerHTML =
      '<a class="radx-brand" href="/radar/metricas" title="Radar · ir al dashboard">' +
        svg('marca', 16) + '<span>Radar</span>' +
      '</a>' +
      '<div class="radx-tabs">' + tabs + '</div>' +
      '<div class="radx-actions">' + tema + '</div>';
    return nav;
  }

  function cargarContadores(nav) {
    var celdas = nav.querySelectorAll('[data-count]');
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
      .catch(function () { /* sin contadores; el navbar sigue usable */ });
  }

  function init() {
    if (document.getElementById('radx-side')) return;
    // dentro de /panel la pagina va en un iframe y el layout lo pone el panel
    if (window.self !== window.top) return;
    // paginas de error/acceso denegado no llevan navbar
    if (document.body.dataset.radxSide === 'off') return;

    var nav = construir();
    document.body.insertBefore(nav, document.body.firstChild);
    document.body.classList.add('radx-has-topbar');

    var btnTema = document.getElementById('radx-theme');
    if (btnTema) {
      btnTema.addEventListener('click', function () {
        var nativo = document.querySelector('#theme-toggle, #themeBtn');
        if (nativo && !nativo.closest('.radx-topbar')) nativo.click();
      });
    }

    cargarContadores(nav);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
