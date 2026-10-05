// Contact form: same delivery as the IT/IAM Help Desk Lab (formsubmit.co, AJAX).
document.getElementById('contact-form').addEventListener('submit', function (event) {
  event.preventDefault();
  var name = document.getElementById('c-name').value.trim();
  var email = document.getElementById('c-email').value.trim();
  var message = document.getElementById('c-message').value.trim();
  var btn = document.getElementById('btn-send');
  var status = document.getElementById('form-status');

  if (!name || !email || !message) {
    status.className = 'form-status error';
    status.textContent = 'Please fill in all fields.';
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Sending...';
  status.className = 'form-status';
  status.textContent = '';

  // Email is encoded to avoid exposing it in plain text in the page source
  var target = atob('ZXJpY2tvbWFyaTI0M0BnbWFpbC5jb20=');

  fetch('https://formsubmit.co/ajax/' + target, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify({ name: name, email: email, message: message, _subject: 'New contact from ' + name + ' — IdentityGuardian AI' })
  })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.success === 'true' || data.success === true) {
        status.className = 'form-status success';
        status.textContent = 'Thank you! Your message has been sent.';
        document.getElementById('contact-form').reset();
      } else {
        status.className = 'form-status error';
        status.textContent = 'Something went wrong. Please try again.';
      }
    })
    .catch(function () {
      status.className = 'form-status error';
      status.textContent = 'Network error. Please try again.';
    })
    .finally(function () {
      btn.disabled = false;
      btn.textContent = 'Send Message';
    });
});
