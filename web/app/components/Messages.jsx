import React from 'react';
import $ from 'jquery';

import { timestamp, classNameFromCategory } from '../utils/formats';

export default class Messages extends React.Component {
  constructor(props) {
    super(props);
    this.highWaterMark= 0
  }
  render() {
    const { messages } = this.props;
    const messageRows = [];
    for (var i = 0; i < messages.length; i++) {
      messageRows.push(<Message key={i} message={messages[i]} />);
    }
    return (
        <table className="messagesTable">
          <tbody>
            {messageRows}
          </tbody>
        </table>
    );
  }

  componentDidUpdate() {
    const { messages } = this.props;
    var high = this.highWaterMark;
    for (var i = 0; i < messages.length; i++) {
      if (messages[i][0] > this.highWaterMark) {
        if (messages[i].length == 5) {
          const carRef = `#car_${messages[i][4]}`;
          $(carRef).fadeTo(300, 0.1).fadeTo(300, 1).fadeTo(300, 0.1).fadeTo(300, 1);
        }
        high = Math.max(messages[i][0], high);
      }
    }
    this.highWaterMark= high;
  }
}

class Message extends React.Component {
  render() {
    const [ time, category, text, messageType ] = this.props.message;
    return (
      <tr>
        <td className="time">{timestamp(time)}</td>
        <td className={`category category-${classNameFromCategory(category)}`}>{category}</td>
        <td className={`text ${messageType}`}>{text}</td>
      </tr>
    );
  }
}