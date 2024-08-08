self.addEventListener('install', function(event) {
    event.waitUntil(
      caches.open('my-cache').then(function(cache) {
        return cache.addAll([
          '/',
          '/index.html',
          '/homeicon.png',
          'https://www.univcoop.jp//favicon.ico',
          'https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css',
          'https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css',
          'https://cdn.jsdelivr.net/npm/flatpickr/dist/themes/material_green.css',
          'https://use.fontawesome.com/releases/v6.5.2/css/all.css',
          'https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700&display=swap',
          'https://cdn.jsdelivr.net/npm/flatpickr'
        ]);
      })
    );
  });
  
  self.addEventListener('fetch', function(event) {
    event.respondWith(
      caches.match(event.request).then(function(response) {
        return response || fetch(event.request);
      })
    );
  });
  