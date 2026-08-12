function applyTheme(dark){
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
  document.getElementById('iconSun').style.display = dark ? 'block' : 'none';
  document.getElementById('iconMoon').style.display = dark ? 'none' : 'block';
}
function toggleTheme(){
  const dark = document.documentElement.getAttribute('data-theme') !== 'dark';
  try { localStorage.setItem('cat-theme', dark ? 'dark' : 'light'); } catch(e){}
  applyTheme(dark);
}
applyTheme((()=>{ try { return localStorage.getItem('cat-theme') === 'dark'; } catch(e){ return false; } })());