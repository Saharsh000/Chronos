// set theme before first paint (no flash)
try {
  var t = localStorage.getItem('chronos-theme');
  if (t) document.documentElement.dataset.theme = t;
  else if (matchMedia('(prefers-color-scheme: light)').matches) document.documentElement.dataset.theme = 'light';
} catch (e) {}
