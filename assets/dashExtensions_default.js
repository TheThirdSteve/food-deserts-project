window.dashExtensions = Object.assign({}, window.dashExtensions, {
    default: {
        function0: function(feature, context) {
            const {
                classes,
                colorscale,
                style,
                colorProp
            } = context.hideout; // get props from hideout
            const value = feature.properties[colorProp]; // get value that determines the color
            if (value == null) {
                style.fillColor = '#808080';
                return style;
            }
            for (let i = 0; i < classes.length; i++) {
                if (value >= classes[i] && value < classes[i + 1]) {
                    style.fillColor = colorscale[i]; // set the fill color according to the class
                    break;
                }
            }
            return style;
        }
    }
});