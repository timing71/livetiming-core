const webpack = require('webpack');
const merge = require('webpack-merge');
const path = require('path');

const TARGET = process.env.npm_lifecycle_event;

const PATHS = {
  app: path.join(__dirname, 'app'),
  build: path.join(__dirname, 'build')
};

process.env.BABEL_ENV = TARGET;

const common = {
  entry: PATHS.app,
  resolve: {
    extensions: ['', '.js', '.jsx']
  },
  output: {
    path: PATHS.build,
    filename: 'bundle.js'
  },
  module: {
   loaders: [
      {
        test: /\.css$/,
        loader: "style!css?sourceMap"
      },
      {
        test: /\.scss$/,
        loader: "style!css?sourceMap!sass?sourceMap"
      },
      {
        test: /\.jsx?$/,
        loaders: ['babel?cacheDirectory'],
        include: PATHS.app
      },
      { test: /\.woff(\?v=[0-9]\.[0-9]\.[0-9])?$/,   loader: "url-loader?limit=10000&mimetype=application/font-woff" },
      { test: /\.woff2(\?v=[0-9]\.[0-9]\.[0-9])?$/,  loader: "url-loader?limit=10000&mimetype=application/font-woff" },
      { test: /\.ttf(\?v=[0-9]\.[0-9]\.[0-9])?$/,    loader: "file-loader" },
      { test: /\.eot(\?v=[0-9]\.[0-9]\.[0-9])?$/,    loader: "file-loader" },
      { test: /\.svg(\?v=[0-9]\.[0-9]\.[0-9])?$/,    loader: "file-loader" },
      { test: /\.png(\?v=[0-9]\.[0-9]\.[0-9])?$/,    loader: "url-loader?limit=100000" }
    ],
    noParse: [/autobahn.js$/]
  }
};


// Default configuration
if(TARGET === 'start' || !TARGET) {
  module.exports = merge(common, {
    devtool: 'eval-source-map',
    devServer: {
      contentBase: PATHS.build,

      // Enable history API fallback so HTML5 History API based
      // routing works. This is a good default that will come
      // in handy in more complicated setups.
      historyApiFallback: true,
      hot: true,
      inline: true,
      progress: true,

      // Display only errors to reduce the amount of output.
      stats: 'errors-only',

      // Parse host and port from env so this is easy to customize.
      host: process.env.HOST,
      port: process.env.PORT
    },
    plugins: [
      new webpack.HotModuleReplacementPlugin()
    ]
  });
}

if(TARGET === 'build') {
  module.exports = merge(common, {});
}
