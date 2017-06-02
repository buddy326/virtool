import React from "react";
import SampleController from "./Manage/Controller";

export default class ManageSamples extends React.Component {

    constructor (props) {
        super(props);

        this.state = {
            documents: dispatcher.db.samples.chain()
        };
    }

    static propTypes = {
        route: React.PropTypes.object
    };

    update = () => {
        this.setState({
            documents: dispatcher.db.samples.chain()
        });
    };

    render () {
        return (
            <SampleController
                route={this.props.route}
                documents={this.state.documents}
            />
        );
    }

}
