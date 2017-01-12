import React from 'react';

const FlagStatusPanel = ({flag, text}) => (<div className={"flag-status flag-status-" + flag}>{text}</div>);

export default FlagStatusPanel;
