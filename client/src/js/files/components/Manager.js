import React from "react";
import { capitalize, forEach, map, some } from "lodash-es";
import { connect } from "react-redux";

import File from "./File";
import { findFiles, removeFile, upload } from "../actions";
import { Alert, LoadingPlaceholder, NoneFound, ViewHeader, UploadBar, ScrollList } from "../../base";
import { createRandomString, checkAdminOrPermission, isArrayEqual } from "../../utils";

const checkArrayIncludes = (l, s) => {

    const longer = l.slice();
    const shorter = s.slice();

    map(shorter, element => {
        if (!some(longer, element)) {
            longer.push(element);
        }
        return element;
    });

    return longer;
};

class FileManager extends React.Component {

    constructor (props) {
        super(props);
        this.state = {
            masterList: this.props.documents,
            list: this.props.documents,
            page: this.props.page
        };
    }

    static getDerivedStateFromProps (nextProps, prevState) {

        if (nextProps.page === 1) {
            return {
                masterList: nextProps.documents,
                list: nextProps.documents,
                page: nextProps.page
            };
        }

        if (prevState.page < nextProps.page) {
            return {
                masterList: checkArrayIncludes(prevState.masterList, nextProps.documents),
                list: nextProps.documents,
                page: nextProps.page
            };
        } else if (!isArrayEqual(prevState.list, nextProps.documents)) {
            return {
                masterList: checkArrayIncludes(prevState.masterList, nextProps.documents),
                list: nextProps.documents
            };
        }
        return null;
    }

    handleRemove = (fileId) => {
        const newArray = map(this.state.masterList, item => {
            if (item.id === fileId) {
                item.pending = "remove";
            }
            return item;
        });

        this.setState({ masterList: newArray });

        this.props.onRemove(fileId);
    };

    rowRenderer = (index) => (
        this.state.masterList[index].pending ? null : (
            <File
                key={this.state.masterList[index].id}
                {...this.state.masterList[index]}
                onRemove={this.handleRemove}
            />
        )
    );

    componentDidMount () {
        this.props.onFind(this.props.fileType);
    }

    handleDrop = (acceptedFiles) => {
        if (this.props.canUpload) {
            this.props.onDrop(this.props.fileType, acceptedFiles);
        }
    };

    handlePage = (page) => {
        this.props.onFind(this.props.fileType, page);
    };

    render () {

        if (this.props.documents === null) {
            return <LoadingPlaceholder />;
        }

        const titleType = this.props.fileType === "reads" ? "Read" : capitalize(this.props.fileType);

        let toolbar;

        if (this.props.canUpload) {
            toolbar = (
                <UploadBar onDrop={this.handleDrop} />
            );
        } else {
            toolbar = (
                <Alert bsStyle="warning" icon="warning">
                    <strong>You do not have permission to upload files.</strong>
                    <span>Contact an administrator.</span>
                </Alert>
            );
        }

        return (
            <div>
                <ViewHeader
                    title={`${titleType} Files`}
                    page={this.props.page}
                    count={this.props.documents.length}
                    foundCount={this.props.found_count}
                    totalCount={this.props.total_count}
                />

                {toolbar}

                {this.props.documents.length ? null : <NoneFound noun="files" />}

                <ScrollList
                    hasNextPage={this.props.page < this.props.page_count}
                    isNextPageLoading={this.props.isLoading}
                    isLoadError={this.props.errorLoad}
                    list={this.state.masterList}
                    loadNextPage={this.handlePage}
                    page={this.state.page}
                    rowRenderer={this.rowRenderer}
                />
            </div>
        );
    }
}

const mapStateToProps = (state) => {
    const { documents, found_count, page, page_count, total_count } = state.files;

    return {
        documents,
        found_count,
        page,
        page_count,
        total_count,
        canUpload: checkAdminOrPermission(state.account.administrator, state.account.permissions, "upload_file")
    };
};

const mapDispatchToProps = (dispatch) => ({

    onDrop: (fileType, acceptedFiles) => {
        forEach(acceptedFiles, file => {
            const localId = createRandomString();
            dispatch(upload(localId, file, fileType));
        });
    },

    onFind: (fileType, page = 1) => {
        dispatch(findFiles(fileType, page));
    },

    onRemove: (fileId) => {
        dispatch(removeFile(fileId));
    }

});

export default connect(mapStateToProps, mapDispatchToProps)(FileManager);
