(function () {
    const mq = window.matchMedia('(max-width: 768px)');

    function setupMobile() {
        if (!mq.matches) return;
        const search = document.getElementById('search-campanas');
        if (search && !search.dataset.mobileAuto) {
            search.dataset.mobileAuto = '1';
            search.addEventListener('focus', () => {
                setTimeout(() => search.scrollIntoView({ behavior: 'smooth', block: 'center' }), 150);
            });
        }

        const modal = document.getElementById('modal-campana');
        if (modal && !modal.dataset.mobileReady) {
            modal.dataset.mobileReady = '1';
            modal.addEventListener('transitionend', () => {
                if (modal.classList.contains('open')) {
                    document.body.classList.add('cm-mobile-lock');
                } else {
                    document.body.classList.remove('cm-mobile-lock');
                }
            });
        }

        const filters = document.getElementById('cm-filters-panel');
        const quickbar = document.querySelector('.cm-quickbar');
        if (quickbar && filters && !quickbar.dataset.filtersReady) {
            quickbar.dataset.filtersReady = '1';
            quickbar.classList.remove('open');
        }
    }

    function syncMobileModalLock() {
        const isOpen = document.getElementById('modal-campana')?.classList.contains('open')
            || document.getElementById('modal-ficha')?.classList.contains('open')
            || document.getElementById('modal-nueva-etiqueta')?.classList.contains('open');
        document.body.classList.toggle('cm-mobile-lock', !!isOpen && mq.matches);
    }

    document.addEventListener('DOMContentLoaded', () => {
        setupMobile();
        syncMobileModalLock();
    });

    window.toggleMobileFilters = function () {
        const quickbar = document.querySelector('.cm-quickbar');
        if (!quickbar || !mq.matches) return;
        quickbar.classList.toggle('open');
        if (quickbar.classList.contains('open')) {
            quickbar.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    };

    const originalAbrirModal = window.abrirModal;
    window.abrirModal = function (id) {
        originalAbrirModal.call(this, id);
        syncMobileModalLock();
    };

    const originalCerrarModal = window.cerrarModal;
    window.cerrarModal = function (id) {
        originalCerrarModal.call(this, id);
        syncMobileModalLock();
    };

    const originalCargarCampanas = window.cargarCampanas;
    if (typeof originalCargarCampanas === 'function') {
        window.cargarCampanas = function () {
            const result = originalCargarCampanas.apply(this, arguments);
            syncMobileModalLock();
            return result;
        };
    }
})();
