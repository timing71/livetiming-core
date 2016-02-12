export function format(value, type) {
  switch (type) {
  case 'time':
    return timeInSeconds(value);
  default:
    return value;
  }
}

export function timeInSeconds(seconds) {
  var minutes = Math.floor(seconds / 60);
  seconds = (seconds - (60 * minutes)).toFixed(3);
  if (minutes < 10) {
    minutes = "0" + minutes;
  }
  if (seconds < 10) {
    seconds = "0" + seconds;
  }
  
  return minutes + ":" + seconds;
}