import React from 'react';
import autobahn from '../lib/autobahn';

export default class App extends React.Component {

  componentWillMount() {
    console.log("Ok, Autobahn loaded", autobahn.version);
  }

  render() {
    return <p>Hello, World!</p>;
  }

}