import moment from 'moment';

export function format(value, type) {
  if (value == "") {
    return "";
  }
  switch (type) {
  case 'time':
    return timeInSeconds(value);
  case 'delta':
    if (isNaN(value)) {
      return value;
    }
    else {
      return parseFloat(value).toFixed(3);
    }
  default:
    return value;
  }
}

export function timeInSeconds(seconds) {
  var minutes = Math.floor(seconds / 60);
  seconds = (seconds - (60 * minutes)).toFixed(3);

  if (seconds < 10) {
    seconds = "0" + seconds;
  }
  
  return minutes + ":" + seconds;
}

export function timeWithHours(seconds) {
  var hours = Math.floor(seconds / 3600);
  seconds = seconds - (3600 * hours);
  var minutes = Math.floor(seconds / 60);
  seconds = (seconds - (60 * minutes)).toFixed(0);
  if (hours < 10) {
    hours = "0" + hours;
  }
  if (minutes < 10) {
    minutes = "0" + minutes;
  }
  if (seconds < 10) {
    seconds = "0" + seconds;
  }
  
  return hours + ":" + minutes + ":" + seconds;
}

export function timestamp(unix) {
  return moment(unix * 1000).format("HH:mm:ss");
}

export function classNameFromCategory(cat) {
  return cat.replace(/ /g, "").toLowerCase();
}