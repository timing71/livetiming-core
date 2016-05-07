import React from 'react';

import { Grid, Row, Col } from 'react-bootstrap';

export default class TrackData extends React.Component {
  render() {
    const { spec, dataset } = this.props;
    
    if (spec && dataset) {
      const data = [];

      for (var i = 0; i < spec.length; i++) {
        data.push(<Col sm={3} className="trackdata-key" key={spec[i]}>{spec[i]}</Col>);
        data.push(<Col sm={3} className="trackdata-value" key={spec[i] + "_value"}>{dataset[i]}</Col>);
      }

      return (
          <Grid fluid={true}>
            <Row>
              {data}
            </Row>
          </Grid>
      );
    }
    else {
      return (<p className="trackdata-key">Track data not available</p>);
    }
  }
}
