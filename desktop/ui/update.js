// Draws what the app says of its update as it goes: a bar that only says it is going, or how far
// a download is where the app knows.

const step = document.getElementById('step')
const bar = document.querySelector('.bar')

function draw({ title, percent }) {
  step.textContent = title
  bar.classList.toggle('determinate', percent != null)
  bar.firstElementChild.style.width = percent == null ? '' : `${percent}%`
}
