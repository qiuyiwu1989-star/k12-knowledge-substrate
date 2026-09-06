document.querySelectorAll('[data-copy]').forEach(button => {
  button.addEventListener('click', async () => {
    const target = document.getElementById(button.dataset.copy);
    const status = document.getElementById('copy-status');
    try {
      await navigator.clipboard.writeText(target.textContent.trim());
      status.textContent = '已复制，请按说明替换本机路径。';
      button.textContent = '已复制 ✓';
    } catch {
      const range = document.createRange();
      range.selectNodeContents(target);
      const selection = window.getSelection();
      selection.removeAllRanges(); selection.addRange(range);
      button.textContent = '请手动复制选中文字';
      status.textContent = '浏览器未允许复制，已选中文字，请手动复制。';
    }
  });
});
