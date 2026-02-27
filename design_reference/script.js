document.addEventListener('DOMContentLoaded', () => {
  const trigger = document.getElementById('user-trigger');
  const panel = document.getElementById('user-panel');

  if (!trigger || !panel) return;

  trigger.addEventListener('click', () => {
    panel.classList.toggle('open');
  });
});


const topLinksWrapper = document.getElementById('top-links-wrapper');
const toggleTopLinks = document.getElementById('toggle-top-links');
const userToggle = document.querySelector('.user-menu-toggle');

// ------------------------
// 1️⃣ Initialize top-links state immediately
// ------------------------
(function() {
  const savedState = localStorage.getItem('topLinksCollapsed');
  
  if (savedState === 'true') {
    topLinksWrapper.classList.remove('visible'); // collapsed
    toggleTopLinks.textContent = '＝';
  } else {
    topLinksWrapper.classList.add('visible'); // visible
    toggleTopLinks.textContent = '×';
  }

  // Remove temporary class to enable transitions after first paint
  topLinksWrapper.classList.remove('collapsed-by-default');
})();

// ------------------------
// 2️⃣ Toggle top-links on button click
// ------------------------
toggleTopLinks.addEventListener('click', () => {
  topLinksWrapper.classList.toggle('visible');

  const isCollapsed = !topLinksWrapper.classList.contains('visible');
  localStorage.setItem('topLinksCollapsed', isCollapsed);

  toggleTopLinks.textContent = isCollapsed ? '＝' : '×';
});

// ------------------------
// 3️⃣ User menu toggle
// ------------------------
userToggle.addEventListener('click', (e) => {
  e.stopPropagation();
  userToggle.classList.toggle('active');
});

// Close user menu when clicking outside
document.addEventListener('click', () => {
  userToggle.classList.remove('active');
});