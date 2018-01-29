import React from "react";
import { map, sortBy } from "lodash-es";
import { connect } from "react-redux";
import { ListGroup, FormGroup, InputGroup, FormControl } from "react-bootstrap";

import { analyze } from "../../actions";
import { Icon, Button, LoadingPlaceholder, NoneFound } from "../../../base";
import AnalysisItem from "./Item";
import CreateAnalysis from "./Create";
import {getCanModify} from "../../selectors";

const AnalysesToolbar = ({ onClick }) => (
    <div className="toolbar">
        <FormGroup>
            <InputGroup>
                <InputGroup.Addon>
                    <Icon name="search" />
                </InputGroup.Addon>
                <FormControl type="text" />
            </InputGroup>
        </FormGroup>
        <Button
            icon="new-entry"
            tip="New Analysis"
            bsStyle="primary"
            onClick={onClick}
        />
    </div>
);

class AnalysesList extends React.Component {

    constructor (props) {
        super(props);
        this.state = {
            show: false
        };
    }

    render () {

        if (this.props.analyses === null) {
            return <LoadingPlaceholder margin="37px" />;
        }

        // The content that will be shown below the "New Analysis" form.
        let listContent;

        if (this.props.analyses.length) {
            // The components that detail individual analyses.
            listContent = map(sortBy(this.props.analyses, "timestamp").reverse(), (document, index) =>
                <AnalysisItem key={index} {...document} />
            );
        } else {
            listContent = <NoneFound noun="analyses" noListGroup />;
        }

        return (
            <div>
                {this.props.canModify ? <AnalysesToolbar onClick={() => this.setState({show: true})} /> : null}

                <ListGroup>
                    {listContent}
                </ListGroup>

                <CreateAnalysis
                    id={this.props.detail.id}
                    show={this.state.show}
                    onHide={() => this.setState({show: false})}
                    onSubmit={this.props.onAnalyze}
                />
            </div>
        );
    }
}

const mapStateToProps = (state) => ({
    detail: state.samples.detail,
    analyses: state.samples.analyses,
    canModify: getCanModify(state)
});

const mapDispatchToProps = (dispatch) => ({

    onAnalyze: (sampleId, algorithm) => {
        dispatch(analyze(sampleId, algorithm));
    }

});

const Container = connect(mapStateToProps, mapDispatchToProps)(AnalysesList);

export default Container;
