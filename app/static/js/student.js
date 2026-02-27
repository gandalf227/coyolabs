(function () {
  const bindToggle = ({ triggerId, panelId, storageKey, classMode = false, openClass = 'open' }) => {
    const trigger = document.getElementById(triggerId);
    const panel = document.getElementById(panelId);
    if (!trigger || !panel) return;

    const readStored = () => localStorage.getItem(storageKey) === '1';
    const apply = (isOpen) => {
      if (classMode) {
        panel.classList.toggle(openClass, isOpen);
      } else {
        panel.hidden = !isOpen;
      }
      localStorage.setItem(storageKey, isOpen ? '1' : '0');
    };

    apply(readStored());
    trigger.addEventListener('click', () => apply(classMode ? !panel.classList.contains(openClass) : panel.hidden));
    document.addEventListener('click', (event) => {
      if (!panel.contains(event.target) && !trigger.contains(event.target)) {
        apply(false);
      }
    });
  };

  bindToggle({ triggerId: 'user-panel-toggle', panelId: 'user-panel', storageKey: 'student:user-panel' });
  bindToggle({ triggerId: 'top-links-toggle', panelId: 'top-links-wrapper', storageKey: 'student:top-links', classMode: true });
})();
