document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-confirm]');
  if (button && !window.confirm(button.dataset.confirm)) event.preventDefault();
});
document.querySelectorAll('form').forEach(form => {
  form.addEventListener('submit', () => {
    // Keep the submitter's name/value available while preventing repeat clicks.
    requestAnimationFrame(() => {
      form.querySelectorAll('button').forEach(button => { button.disabled = true; });
    });
  });
});
