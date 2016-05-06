import React from 'react';

import { timestamp, classNameFromCategory } from '../utils/formats';

export default class Messages extends React.Component {
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