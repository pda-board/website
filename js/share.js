/* Share menus and buttons for events (no dependencies).
   Without JavaScript the menus still open (they are <details> elements)
   and every option except "Copy link" / native share is a plain link. */
(function () {
  function closest(el, sel) {
    while (el && el.nodeType === 1) { if (el.matches(sel)) return el; el = el.parentElement; }
    return null;
  }
  function shareData(el) {
    var box = closest(el, '[data-share-url]');
    if (!box) return null;
    return {
      title: box.getAttribute('data-share-title') || document.title,
      text: box.getAttribute('data-share-text') || '',
      url: box.getAttribute('data-share-url')
    };
  }
  function announce(el, msg) {
    var box = closest(el, '[data-share-url]') || document.body;
    var live = box.querySelector('.share-live');
    if (live) { live.textContent = ''; setTimeout(function () { live.textContent = msg; }, 30); }
  }

  // Popover menus
  var menus = Array.prototype.slice.call(document.querySelectorAll('details.share'));
  menus.forEach(function (d) {
    var summary = d.querySelector('summary');
    summary.setAttribute('aria-expanded', d.open ? 'true' : 'false');
    d.addEventListener('toggle', function () {
      summary.setAttribute('aria-expanded', d.open ? 'true' : 'false');
      if (d.open) menus.forEach(function (o) { if (o !== d) o.open = false; });
    });
    d.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && d.open) { e.preventDefault(); d.open = false; summary.focus(); }
    });
  });
  document.addEventListener('click', function (e) {
    menus.forEach(function (d) { if (d.open && !d.contains(e.target)) d.open = false; });
  });

  // Native share sheet (phones: Instagram, WhatsApp, Teams, ...)
  if (navigator.share) {
    document.querySelectorAll('[data-native-share]').forEach(function (b) {
      b.hidden = false;
      b.addEventListener('click', function () {
        var data = shareData(b);
        if (data) navigator.share(data).catch(function () {});
      });
    });
  }

  // Copy link, with a visible confirmation
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    return new Promise(function (resolve, reject) {
      var ta = document.createElement('textarea');
      ta.value = text; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy') ? resolve() : reject(); } catch (err) { reject(err); }
      document.body.removeChild(ta);
    });
  }
  document.querySelectorAll('[data-copy]').forEach(function (a) {
    a.addEventListener('click', function (e) {
      var data = shareData(a);
      if (!data) return;
      e.preventDefault();
      var label = a.querySelector('.label') || a;
      var original = label.getAttribute('data-label') || label.textContent;
      label.setAttribute('data-label', original);
      copyText(data.url).then(function () {
        label.textContent = 'Copied'; label.classList.add('copied');
        announce(a, 'Link copied to the clipboard');
        setTimeout(function () { label.textContent = original; label.classList.remove('copied'); }, 2200);
      }, function () {
        window.prompt('Copy this link:', data.url);
      });
    });
  });
})();
